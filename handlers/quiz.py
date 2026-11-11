import random
import uuid
from typing import Dict, Any
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from states.bot_states import QuizStates
from database.queries import (
    get_user_units,
    get_practice_words,
    get_random_distractors,
    record_answer,
)
from keyboards.inline import get_practice_filter_keyboard, get_quiz_options_keyboard
from keyboards.reply import get_main_keyboard
from utils.ui_helpers import progress_bar

router = Router()

QUIZ_SESSIONS: Dict[str, Dict[str, Any]] = {}

@router.message(F.text == "⚡ Test rejimi (Quiz)")
@router.message(F.text == "🅰️ Test rejimi (Quiz)")
async def start_quiz_menu(message: Message):
    user_id = message.from_user.id
    units = await get_user_units(user_id)
    
    buttons = []
    buttons.append([InlineKeyboardButton(text="🌐 Barcha so'zlarimdan", callback_data="quiz_select_unit:all")])
    for u in units:
        buttons.append([InlineKeyboardButton(text=f"📁 {u['name']} ({u.get('word_count', 0)} ta)", callback_data=f"quiz_select_unit:{u['id']}")])
    buttons.append([InlineKeyboardButton(text="🔙 Bekor qilish", callback_data="back_to_menu")])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer(
        "⚡ <b>SMART TEST (QUIZ) REJIMI:</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Qaysi to'plamdagi so'zlardan test topshirmoqchisiz?",
        reply_markup=keyboard,
        parse_mode="HTML"
    )

@router.callback_query(F.data.startswith("unit_quiz:"))
async def cb_unit_quiz_direct(callback: CallbackQuery):
    unit_id = callback.data.split(":")[1]
    kb = get_practice_filter_keyboard(prefix="quiz_filter", unit_id=int(unit_id))
    await callback.message.edit_text(
        "🎯 <b>Test toifasini tanlang:</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Qaysi so'zlarni mustahkamlaymiz?",
        reply_markup=kb,
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("quiz_select_unit:"))
async def cb_select_quiz_unit(callback: CallbackQuery):
    unit_arg = callback.data.split(":")[1]
    unit_id = None if unit_arg == "all" else int(unit_arg)
    kb = get_practice_filter_keyboard(prefix="quiz_filter", unit_id=unit_id)
    await callback.message.edit_text(
        "🎯 <b>Test toifasini tanlang:</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Qaysi so'zlarni mustahkamlaymiz?",
        reply_markup=kb,
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("quiz_filter:"))
async def cb_start_quiz_session(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    unit_str = parts[1]
    status_filter = parts[2]
    
    unit_id = None if unit_str == "all" else int(unit_str)
    filter_val = None if status_filter == "all" else status_filter
    
    user_id = callback.from_user.id
    words = await get_practice_words(user_id, unit_id=unit_id, status_filter=filter_val, limit=20)
    
    if not words:
        await callback.answer("Tanlangan toifada so'zlar topilmadi!", show_alert=True)
        return

    random.shuffle(words)
    session_id = str(uuid.uuid4())[:8]
    QUIZ_SESSIONS[session_id] = {
        "user_id": user_id,
        "words": words,
        "current_index": 0,
        "correct": 0,
        "wrong": 0,
        "current_options": [],
        "correct_index": 0
    }
    
    await state.set_state(QuizStates.in_progress)
    await send_quiz_question(callback.message, session_id, is_edit=True)
    await callback.answer()

async def send_quiz_question(message: Message, session_id: str, is_edit: bool = False):
    session = QUIZ_SESSIONS.get(session_id)
    if not session:
        await message.answer("Test sessiyasi topilmadi yoki yakunlangan.", reply_markup=get_main_keyboard())
        return

    idx = session["current_index"]
    words = session["words"]
    total = len(words)
    
    if idx >= total:
        await finish_quiz(message, session_id, is_edit)
        return

    current_word = words[idx]
    correct_trans = current_word["translation"]
    
    distractors = await get_random_distractors(session["user_id"], current_word["id"], count=3)
    options = distractors + [correct_trans]
    random.shuffle(options)
    
    session["current_options"] = options
    session["correct_index"] = options.index(correct_trans)
    
    pos = f" <i>({current_word['part_of_speech']})</i>" if current_word.get('part_of_speech') else ""
    trans = f" [<code>{current_word['transcription']}</code>]" if current_word.get('transcription') else ""
    bar = progress_bar(idx + 1, total, length=8)
    
    text = (
        f"⚡ <b>Savol {idx + 1}/{total}</b>  {bar}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🇬🇧 <b>{current_word['word'].upper()}</b>{pos}{trans}\n\n"
        f"<i>To'g'ri o'zbekcha tarjimani tanlang:</i>\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )
    
    kb = get_quiz_options_keyboard(options, session["correct_index"], session_id)
    
    if is_edit:
        await message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    else:
        await message.answer(text, reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data.startswith("qz:"))
async def cb_handle_quiz_answer(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    session_id = parts[1]
    ans_idx_str = parts[2]
    
    session = QUIZ_SESSIONS.get(session_id)
    if not session:
        await callback.answer("Sessiya eskirgan.", show_alert=True)
        return

    if ans_idx_str == "stop":
        await finish_quiz(callback.message, session_id, is_edit=True)
        await callback.answer()
        return

    ans_idx = int(ans_idx_str)
    idx = session["current_index"]
    current_word = session["words"][idx]
    is_correct = (ans_idx == session["correct_index"])
    
    user_id = callback.from_user.id
    new_status = await record_answer(user_id, current_word["id"], is_correct)
    
    if is_correct:
        session["correct"] += 1
        status_note = " (🟢 Yodlandi!)" if new_status == "mastered" else ""
        await callback.answer(f"✅ Barakalla, to'g'ri!{status_note}", show_alert=False)
    else:
        session["wrong"] += 1
        correct_trans = current_word["translation"]
        await callback.answer(f"❌ Noto'g'ri!\nTo'g'ri javob: {correct_trans}\n(🔴 Bilmaganlar ro'yxatiga olindi)", show_alert=True)
        
    session["current_index"] += 1
    await send_quiz_question(callback.message, session_id, is_edit=True)

async def finish_quiz(message: Message, session_id: str, is_edit: bool = True):
    session = QUIZ_SESSIONS.pop(session_id, None)
    if not session:
        return

    total = session["correct"] + session["wrong"]
    correct = session["correct"]
    percent = round((correct / total * 100), 1) if total > 0 else 0

    badge = "🏆 A'lo Natija!" if percent >= 85 else ("👍 Yaxshi Natija!" if percent >= 60 else "💪 Ko'proq Mashq Qiling!")
    bar = progress_bar(correct, total, length=10)
    
    report = (
        f"{badge}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 <b>Aniqlik darajasi: {percent}%</b>\n"
        f"<code>{bar}</code>\n\n"
        f"• ✅ To'g'ri javoblar: <b>{correct} ta</b>\n"
        f"• ❌ Xatolar: <b>{session['wrong']} ta</b>\n"
        f"• 📚 Jami savollar: <b>{total} ta</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💡 <i>Xato qilingan so'zlar 🔴 'Bilmaganlarim' to'plamiga olindi. Keyingi safar ularni alohida mashq qilishingiz mumkin!</i>"
    )
    
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Yana test topshirish", callback_data="quiz_select_unit:all")],
            [InlineKeyboardButton(text="🔙 Asosiy menyu", callback_data="back_to_menu")]
        ]
    )
    
    if is_edit:
        await message.edit_text(report, reply_markup=kb, parse_mode="HTML")
    else:
        await message.answer(report, reply_markup=kb, parse_mode="HTML")
