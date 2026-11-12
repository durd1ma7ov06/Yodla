import html
import random
import re
import uuid
from typing import Dict, Any, List
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from states.bot_states import QuizStates
from database.queries import (
    get_user_units,
    get_practice_words,
    get_auto_quiz_distractors,
    record_answer,
)
from keyboards.inline import get_practice_filter_keyboard
from keyboards.reply import get_main_keyboard
from utils.ui_helpers import progress_bar

router = Router()

CONTEXT_SESSIONS: Dict[str, Dict[str, Any]] = {}
_LETTERS = ["A", "B", "C", "D"]


def _mask_word_in_sentence(sentence: str, word: str) -> str:
    """Replaces the target word in sentence with a blank underline ________."""
    pattern = r"(?i)\b" + re.escape(word.strip()) + r"(?:s|es|ed|ing|d)?\b"
    masked = re.sub(pattern, "<u>________</u>", sentence)
    if "<u>________</u>" not in masked:
        # Fallback simple replacement
        masked = re.sub(re.escape(word.strip()), "<u>________</u>", sentence, flags=re.IGNORECASE)
    return masked


def _build_context_kb(options: List[str], session_id: str, q_idx: int) -> InlineKeyboardMarkup:
    rows = []
    for i, opt in enumerate(options):
        rows.append([
            InlineKeyboardButton(
                text=f"{_LETTERS[i]}) {opt}",
                callback_data=f"cq:{session_id}:{q_idx}:{i}",
            )
        ])
    rows.append([InlineKeyboardButton(text="🛑 Testni yakunlash", callback_data=f"cq:{session_id}:{q_idx}:stop")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(F.text == "🧩 Gap to'ldirish (Kontekst)")
async def start_context_menu(message: Message):
    user_id = message.from_user.id
    units = await get_user_units(user_id)

    buttons = [[InlineKeyboardButton(text="🌐 Barcha so'zlarimdan", callback_data="ctx_select_unit:all")]]
    for u in units:
        buttons.append([
            InlineKeyboardButton(
                text=f"📁 {u['name']} ({u.get('word_count', 0)} ta)",
                callback_data=f"ctx_select_unit:{u['id']}",
            )
        ])
    buttons.append([InlineKeyboardButton(text="🔙 Bekor qilish", callback_data="back_to_menu")])

    await message.answer(
        "🧩 <b>GAP TO'LDIRISH (KONTEKST TESTI):</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "IELTS va CEFR darajasida so'zni gap ichida to'g'ri qo'llash mashqi!\n"
        "Bot gap beradi, siz tushirib qoldirilgan so'zni 4 ta variant orasidan topasiz.\n\n"
        "<i>Qaysi to'plamdan test topshirasiz?</i>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("unit_context:"))
async def cb_unit_context_direct(callback: CallbackQuery):
    unit_id = int(callback.data.split(":")[1])
    kb = get_practice_filter_keyboard(prefix="ctx_filter", unit_id=unit_id)
    await callback.message.edit_text(
        "🧩 <b>Kontekst testi toifasini tanlang:</b>\n━━━━━━━━━━━━━━━━━━━━",
        reply_markup=kb,
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("ctx_select_unit:"))
async def cb_ctx_select_unit(callback: CallbackQuery):
    arg = callback.data.split(":")[1]
    unit_id = None if arg == "all" else int(arg)
    kb = get_practice_filter_keyboard(prefix="ctx_filter", unit_id=unit_id)
    await callback.message.edit_text(
        "🧩 <b>Kontekst testi toifasini tanlang:</b>\n━━━━━━━━━━━━━━━━━━━━",
        reply_markup=kb,
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("ctx_filter:"))
async def cb_start_context_session(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    unit_id = None if parts[1] == "all" else int(parts[1])
    filter_val = None if parts[2] == "all" else parts[2]

    user_id = callback.from_user.id
    raw_words = await get_practice_words(user_id, unit_id=unit_id, status_filter=filter_val, limit=30)
    # Filter words that have a valid example sentence
    words = [
        w for w in raw_words
        if (w.get("example_en") or "").strip() and (w.get("word") or "").strip()
    ]

    if not words:
        await callback.answer(
            "Bu toifada misol gapi mavjud bo'lgan so'zlar topilmadi!",
            show_alert=True,
        )
        return

    random.shuffle(words)
    words = words[:15]
    session_id = str(uuid.uuid4())[:8]
    CONTEXT_SESSIONS[session_id] = {
        "user_id": user_id,
        "words": words,
        "current_index": 0,
        "correct": 0,
        "wrong": 0,
    }

    await send_context_question(callback.message, session_id, is_edit=True)
    await callback.answer()


async def send_context_question(message: Message, session_id: str, is_edit: bool = False):
    session = CONTEXT_SESSIONS.get(session_id)
    if not session:
        await message.answer("Test sessiyasi topilmadi.", reply_markup=get_main_keyboard())
        return

    idx = session["current_index"]
    words = session["words"]
    total = len(words)

    if idx >= total:
        await finish_context_quiz(message, session_id, is_edit)
        return

    current_word = words[idx]
    correct_word = current_word["word"].strip()

    distractors = await get_auto_quiz_distractors(
        session["user_id"], current_word["id"], correct_word, field="word", count=3
    )
    options = distractors + [correct_word]
    random.shuffle(options)

    session["current_options"] = options
    session["correct_index"] = options.index(correct_word)

    masked_en = _mask_word_in_sentence(current_word["example_en"], correct_word)
    bar = progress_bar(idx + 1, total, length=8)

    uz_hint = f"\n🇺🇿 <i>Tarjimasi: ({html.escape(current_word['example_uz'])})</i>" if current_word.get("example_uz") else ""
    text = (
        f"🧩 <b>Savol {idx + 1}/{total}</b>  {bar}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💬 <b>\"{masked_en}\"</b>{uz_hint}\n\n"
        f"❓ <i>Tushirib qoldirilgan to'g'ri so'zni tanlang:</i>\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )

    kb = _build_context_kb(options, session_id, idx)
    if is_edit:
        await message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    else:
        await message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data.startswith("cq:"))
async def cb_handle_context_answer(callback: CallbackQuery):
    parts = callback.data.split(":")
    session_id = parts[1]
    q_idx = int(parts[2])
    ans_str = parts[3]

    session = CONTEXT_SESSIONS.get(session_id)
    if not session or session["user_id"] != callback.from_user.id:
        await callback.answer("Sessiya eskirgan.", show_alert=True)
        return

    if session["current_index"] != q_idx:
        await callback.answer("Bu savolga allaqachon javob berilgan!", show_alert=False)
        return

    if ans_str == "stop":
        await finish_context_quiz(callback.message, session_id, is_edit=True)
        await callback.answer()
        return

    ans_idx = int(ans_str)
    current_word = session["words"][q_idx]
    is_correct = ans_idx == session["correct_index"]
    new_status = await record_answer(callback.from_user.id, current_word["id"], is_correct)

    if is_correct:
        session["correct"] += 1
        status_note = " (🟢 Yodlandi!)" if new_status == "mastered" else ""
        await callback.answer(f"✅ To'g'ri! {current_word['word']}{status_note}", show_alert=False)
    else:
        session["wrong"] += 1
        await callback.answer(
            f"❌ Noto'g'ri!\nTo'g'ri so'z: {current_word['word']} ({current_word['translation']})",
            show_alert=True,
        )

    session["current_index"] += 1
    await send_context_question(callback.message, session_id, is_edit=True)


async def finish_context_quiz(message: Message, session_id: str, is_edit: bool = True):
    session = CONTEXT_SESSIONS.pop(session_id, None)
    if not session:
        return

    total = session["correct"] + session["wrong"]
    correct = session["correct"]
    percent = round((correct / total * 100), 1) if total > 0 else 0

    badge = "🏆 Kontekstni Mukammal Tushunasiz!" if percent >= 85 else ("👍 Yaxshi Natija!" if percent >= 60 else "💪 Ko'proq Mashq Qiling!")
    bar = progress_bar(correct, total, length=10)

    report = (
        f"🧩 <b>GAP TO'LDIRISH TESTI YAKUNLANDI!</b>\n"
        f"{badge}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 <b>Aniqlik darajasi: {percent}%</b>\n"
        f"<code>{bar}</code>\n\n"
        f"• ✅ To'g'ri topilganlar: <b>{correct} ta</b>\n"
        f"• ❌ Xatolar: <b>{session['wrong']} ta</b>\n"
        f"• 📚 Jami savollar: <b>{total} ta</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💡 <i>Mashqlaringiz kunlik 🔥 Streak hisobingizga qo'shildi!</i>"
    )

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Yana mashq qilish", callback_data="ctx_select_unit:all")],
            [InlineKeyboardButton(text="🔙 Asosiy menyu", callback_data="back_to_menu")],
        ]
    )
    if is_edit:
        await message.edit_text(report, reply_markup=kb, parse_mode="HTML")
    else:
        await message.answer(report, reply_markup=kb, parse_mode="HTML")
