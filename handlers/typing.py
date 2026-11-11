import random
import uuid
from typing import Dict, Any
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
from aiogram.fsm.context import FSMContext

from states.bot_states import TypingStates
from database.queries import (
    get_user_units,
    get_practice_words,
    record_answer,
)
from keyboards.inline import get_practice_filter_keyboard, get_typing_action_keyboard
from keyboards.reply import get_main_keyboard
from services.tts_service import generate_speech_bytes
from utils.ui_helpers import progress_bar

router = Router()

TYPING_SESSIONS: Dict[int, Dict[str, Any]] = {}

def create_mask(word: str, revealed_count: int = 1) -> str:
    word = word.strip()
    if len(word) <= 2:
        return word[0] + " _"
    
    revealed = word[:revealed_count]
    rest = " _" * (len(word) - revealed_count)
    return revealed + rest

def levenshtein_distance(s1: str, s2: str) -> int:
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    return previous_row[-1]

@router.message(F.text == "✍️ Imlo mashqi (Spelling)")
@router.message(F.text == "✍️ Yozma mashq (Spelling)")
async def start_typing_menu(message: Message):
    user_id = message.from_user.id
    units = await get_user_units(user_id)
    
    buttons = []
    buttons.append([InlineKeyboardButton(text="🌐 Barcha so'zlarimdan", callback_data="typing_select_unit:all")])
    for u in units:
        buttons.append([InlineKeyboardButton(text=f"📁 {u['name']} ({u.get('word_count', 0)} ta)", callback_data=f"typing_select_unit:{u['id']}")])
    buttons.append([InlineKeyboardButton(text="🔙 Bekor qilish", callback_data="back_to_menu")])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer(
        "✍️ <b>IMLO MASHQI (SPELLING) REJIMI:</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Qaysi to'plam so'zlaridan yozish mashqini boshlaymiz?",
        reply_markup=keyboard,
        parse_mode="HTML"
    )

@router.callback_query(F.data.startswith("unit_typing:"))
async def cb_unit_typing_direct(callback: CallbackQuery):
    unit_id = callback.data.split(":")[1]
    kb = get_practice_filter_keyboard(prefix="typing_filter", unit_id=int(unit_id))
    await callback.message.edit_text(
        "🎯 <b>Yozma mashq toifasini tanlang:</b>\n━━━━━━━━━━━━━━━━━━━━",
        reply_markup=kb,
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("typing_select_unit:"))
async def cb_select_typing_unit(callback: CallbackQuery):
    unit_arg = callback.data.split(":")[1]
    unit_id = None if unit_arg == "all" else int(unit_arg)
    kb = get_practice_filter_keyboard(prefix="typing_filter", unit_id=unit_id)
    await callback.message.edit_text(
        "🎯 <b>Yozma mashq toifasini tanlang:</b>\n━━━━━━━━━━━━━━━━━━━━",
        reply_markup=kb,
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("typing_filter:"))
async def cb_start_typing_session(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    unit_str = parts[1]
    status_filter = parts[2]
    
    unit_id = None if unit_str == "all" else int(unit_str)
    filter_val = None if status_filter == "all" else status_filter
    
    user_id = callback.from_user.id
    words = await get_practice_words(user_id, unit_id=unit_id, status_filter=filter_val, limit=15)
    
    if not words:
        await callback.answer("Tanlangan toifada so'zlar topilmadi!", show_alert=True)
        return

    random.shuffle(words)
    TYPING_SESSIONS[user_id] = {
        "words": words,
        "current_index": 0,
        "revealed_letters": 1,
        "correct": 0,
        "wrong": 0
    }
    
    await state.set_state(TypingStates.in_progress)
    await callback.message.delete()
    await send_typing_prompt(callback.message, user_id)
    await callback.answer()

async def send_typing_prompt(message: Message, user_id: int):
    session = TYPING_SESSIONS.get(user_id)
    if not session:
        return

    idx = session["current_index"]
    words = session["words"]
    total = len(words)
    
    if idx >= total:
        await finish_typing(message, user_id)
        return

    current_word = words[idx]
    mask = create_mask(current_word["word"], session.get("revealed_letters", 1))
    pos = f" <i>({current_word['part_of_speech']})</i>" if current_word.get('part_of_speech') else ""
    bar = progress_bar(idx + 1, total, length=8)
    
    text = (
        f"✍️ <b>So'z {idx + 1}/{total}</b>  {bar}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🇺🇿 <b>Ma'nosi:</b> {current_word['translation']}{pos}\n"
        f"🔤 <b>Imlo andozasi:</b> <code>{mask}</code> ({len(current_word['word'])} ta harf)\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>Inglizcha to'g'ri so'zni xabarda yozib yuboring:</i>"
    )
    
    kb = get_typing_action_keyboard(current_word["id"])
    await message.answer(text, reply_markup=kb, parse_mode="HTML")

@router.message(TypingStates.in_progress, F.text)
async def process_typing_answer(message: Message, state: FSMContext):
    user_id = message.from_user.id
    session = TYPING_SESSIONS.get(user_id)
    
    if not session:
        await state.clear()
        await message.answer("Mashq yakunlangan.", reply_markup=get_main_keyboard())
        return

    idx = session["current_index"]
    current_word = session["words"][idx]
    
    user_input = message.text.strip().lower()
    target_word = current_word["word"].strip().lower()

    if user_input in ["/stop", "stop", "to'xtatish", "🔙 bekor qilish"]:
        await finish_typing(message, user_id)
        await state.clear()
        return

    # Check exact match
    if user_input == target_word:
        session["correct"] += 1
        new_status = await record_answer(user_id, current_word["id"], is_correct=True)
        status_note = " (🟢 Yodlandi!)" if new_status == "mastered" else ""
        
        reply_txt = (
            f"🎉 <b>Ajoyib, to'liq to'g'ri!</b>{status_note}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🇬🇧 <b>{current_word['word'].upper()}</b> [<code>{current_word.get('transcription', '')}</code>]\n"
            f"🇺🇿 {current_word['translation']}"
        )
        if current_word.get("example_en"):
            reply_txt += f"\n\n💬 <i>\"{current_word['example_en']}\"</i>"

        await message.answer(reply_txt, parse_mode="HTML")
        
        # Audio pronunciation
        try:
            audio_fp = await generate_speech_bytes(current_word["word"])
            voice_file = BufferedInputFile(audio_fp.read(), filename="pronunciation.mp3")
            await message.answer_voice(voice=voice_file)
        except Exception:
            pass

        session["current_index"] += 1
        session["revealed_letters"] = 1
        await send_typing_prompt(message, user_id)

    else:
        dist = levenshtein_distance(user_input, target_word)
        if dist <= 2 and len(target_word) >= 4:
            await message.answer(
                f"⚠️ <b>Deyarli to'g'ri!</b> Kichik harf xatosi bor.\n"
                f"Diqqat bilan qayta yozib ko'ring (yoki 💡 <i>Maslahat</i> tugmasini bosing)."
            )
        else:
            session["wrong"] += 1
            await record_answer(user_id, current_word["id"], is_correct=False)
            
            await message.answer(
                f"❌ <b>Noto'g'ri!</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"To'g'ri imlosi: <b>{current_word['word'].upper()}</b> [<code>{current_word.get('transcription', '')}</code>]\n"
                f"<i>(So'z 🔴 Bilmaganlar ro'yxatiga olindi)</i>",
                parse_mode="HTML"
            )
            
            # Send audio
            try:
                audio_fp = await generate_speech_bytes(current_word["word"])
                voice_file = BufferedInputFile(audio_fp.read(), filename="pronunciation.mp3")
                await message.answer_voice(voice=voice_file)
            except Exception:
                pass

            session["current_index"] += 1
            session["revealed_letters"] = 1
            await send_typing_prompt(message, user_id)

@router.callback_query(F.data.startswith("tts_word:"))
async def cb_play_tts(callback: CallbackQuery):
    user_id = callback.from_user.id
    session = TYPING_SESSIONS.get(user_id)
    if not session:
        await callback.answer()
        return

    idx = session["current_index"]
    current_word = session["words"][idx]
    
    try:
        audio_fp = await generate_speech_bytes(current_word["word"])
        voice_file = BufferedInputFile(audio_fp.read(), filename="pronunciation.mp3")
        await callback.message.answer_voice(voice=voice_file, caption=f"🔊 Talaffuz: <code>{current_word['transcription']}</code>", parse_mode="HTML")
        await callback.answer()
    except Exception:
        await callback.answer("Ovoz yuklanmadi.", show_alert=True)

@router.callback_query(F.data == "typing_hint")
async def cb_typing_hint(callback: CallbackQuery):
    user_id = callback.from_user.id
    session = TYPING_SESSIONS.get(user_id)
    if not session:
        await callback.answer()
        return

    idx = session["current_index"]
    current_word = session["words"][idx]
    word_len = len(current_word["word"])
    total = len(session["words"])
    
    current_rev = session.get("revealed_letters", 1)
    if current_rev < word_len:
        session["revealed_letters"] = current_rev + 1
        
    mask = create_mask(current_word["word"], session["revealed_letters"])
    bar = progress_bar(idx + 1, total, length=8)
    
    await callback.message.edit_text(
        f"✍️ <b>So'z {idx + 1}/{total}</b>  {bar} (💡 Maslahat)\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🇺🇿 <b>Ma'nosi:</b> {current_word['translation']}\n"
        f"🔤 <b>Imlo andozasi:</b> <code>{mask}</code> ({word_len} ta harf)\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>Inglizcha to'g'ri so'zni xabarda yozib yuboring:</i>",
        reply_markup=get_typing_action_keyboard(current_word["id"]),
        parse_mode="HTML"
    )
    await callback.answer("Keyingi harf ochildi!")

@router.callback_query(F.data == "typing_skip")
async def cb_typing_skip(callback: CallbackQuery):
    user_id = callback.from_user.id
    session = TYPING_SESSIONS.get(user_id)
    if not session:
        await callback.answer()
        return

    idx = session["current_index"]
    current_word = session["words"][idx]
    session["wrong"] += 1
    await record_answer(user_id, current_word["id"], is_correct=False)
    
    await callback.message.answer(
        f"⏭ <b>O'tkazib yuborildi.</b>\nTo'g'ri javob: <b>{current_word['word'].upper()}</b> — {current_word['translation']}",
        parse_mode="HTML"
    )
    
    session["current_index"] += 1
    session["revealed_letters"] = 1
    await send_typing_prompt(callback.message, user_id)
    await callback.answer()

@router.callback_query(F.data == "typing_stop")
async def cb_typing_stop(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    await finish_typing(callback.message, user_id)
    await state.clear()
    await callback.answer()

async def finish_typing(message: Message, user_id: int):
    session = TYPING_SESSIONS.pop(user_id, None)
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
        f"📊 <b>Imlo mashqi natijasi: {percent}%</b>\n"
        f"<code>{bar}</code>\n\n"
        f"• ✅ To'g'ri yozilgan: <b>{correct} ta</b>\n"
        f"• ❌ Xato / O'tkazilgan: <b>{session['wrong']} ta</b>\n"
        f"• 📚 Jami so'zlar: <b>{total} ta</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💡 <i>Xatolar tahlil qilindi va 🔴 'Bilmaganlarim'ga belgilandi. Keyingi mashqlarda ushbu so'zlar qayta mustahkamlanadi!</i>"
    )
    await message.answer(report, reply_markup=get_main_keyboard(), parse_mode="HTML")
