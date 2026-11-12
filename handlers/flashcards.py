import html
import logging
import random
import uuid
from typing import Dict, Any
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
from aiogram.fsm.context import FSMContext

from database.queries import (
    get_user_units,
    get_practice_words,
    record_answer,
)
from keyboards.inline import get_practice_filter_keyboard
from keyboards.reply import get_main_keyboard
from services.tts_service import generate_speech_bytes
from utils.ui_helpers import progress_bar

logger = logging.getLogger(__name__)
router = Router()

FLASHCARD_SESSIONS: Dict[str, Dict[str, Any]] = {}


def _build_card_text(word: Dict[str, Any], idx: int, total: int, revealed: bool) -> str:
    bar = progress_bar(idx + 1, total, length=8)
    status = word.get("status", "learning")
    badge = "🔴 Qiyin" if status == "unknown" else ("🟢 Yodlangan" if status == "mastered" else "🟡 Yangi")
    pos = f" <i>({html.escape(word['part_of_speech'])})</i>" if word.get("part_of_speech") else ""
    ipa = f" [<code>{html.escape(word['transcription'])}</code>]" if word.get("transcription") else ""
    uz_pron = f"\n🗣 <b>O'qilishi:</b> <i>[{html.escape(word['uz_pronunciation'])}]</i>" if word.get("uz_pronunciation") else ""

    text = (
        f"🃏 <b>Karta {idx + 1}/{total}</b>  {bar}  •  {badge}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🇬🇧 <b>{html.escape(word['word'].upper())}</b>{pos}{ipa}{uz_pron}\n"
    )

    if not revealed:
        text += (
            "\n<i>🤔 So'zni eslashga harakat qiling, tinglang yoki tarjimasini oching:</i>\n"
            "━━━━━━━━━━━━━━━━━━━━"
        )
    else:
        text += f"\n🇺🇿 <b>Tarjimasi:</b> {html.escape(word['translation'])}"
        if word.get("example_en"):
            text += f"\n\n💬 <i>\"{html.escape(word['example_en'])}\"</i>"
            if word.get("example_uz"):
                text += f"\n🇺🇿 <i>({html.escape(word['example_uz'])})</i>"
        text += "\n━━━━━━━━━━━━━━━━━━━━\n<i>O'zingizni baholang:</i>"
    return text


def _build_card_kb(session_id: str, idx: int, revealed: bool) -> InlineKeyboardMarkup:
    if not revealed:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="👁 Tarjimani ochish", callback_data=f"fc_flip:{session_id}:{idx}")],
                [
                    InlineKeyboardButton(text="🔊 Tinglash", callback_data=f"fc_tts:{session_id}:{idx}:0"),
                    InlineKeyboardButton(text="🐢 Sekin eshitish", callback_data=f"fc_tts:{session_id}:{idx}:1"),
                ],
                [InlineKeyboardButton(text="🛑 Yakunlash", callback_data=f"fc_stop:{session_id}")],
            ]
        )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Bildim / Yodladim", callback_data=f"fc_rate:{session_id}:{idx}:1"),
                InlineKeyboardButton(text="🔴 Hali qiyin", callback_data=f"fc_rate:{session_id}:{idx}:0"),
            ],
            [
                InlineKeyboardButton(text="🔊 Tinglash", callback_data=f"fc_tts:{session_id}:{idx}:0"),
                InlineKeyboardButton(text="🐢 Sekin eshitish", callback_data=f"fc_tts:{session_id}:{idx}:1"),
            ],
            [InlineKeyboardButton(text="🛑 Yakunlash", callback_data=f"fc_stop:{session_id}")],
        ]
    )


@router.message(F.text == "🃏 Flashcard (Karta)")
async def start_flashcard_menu(message: Message):
    user_id = message.from_user.id
    units = await get_user_units(user_id)

    buttons = [[InlineKeyboardButton(text="🌐 Barcha so'zlarimdan", callback_data="fc_select_unit:all")]]
    for u in units:
        buttons.append([
            InlineKeyboardButton(
                text=f"📁 {u['name']} ({u.get('word_count', 0)} ta)",
                callback_data=f"fc_select_unit:{u['id']}",
            )
        ])
    buttons.append([InlineKeyboardButton(text="🔙 Bekor qilish", callback_data="back_to_menu")])

    await message.answer(
        "🃏 <b>FLASHCARD (KARTOCHKALAR BILAN YODLASH):</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Boshlang'ich o'quvchilar uchun eng qulay usul — har bir so'zni 🔊 audiosi, "
        "🗣 o'zbekcha o'qilishi va misol gapi bilan bitta-bitta ko'rib yodlash!\n\n"
        "Qaysi to'plamni ochamiz?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("unit_flashcards:"))
async def cb_unit_flashcards_direct(callback: CallbackQuery):
    unit_id = int(callback.data.split(":")[1])
    kb = get_practice_filter_keyboard(prefix="fc_filter", unit_id=unit_id)
    await callback.message.edit_text(
        "🃏 <b>Flashcard toifasini tanlang:</b>\n━━━━━━━━━━━━━━━━━━━━",
        reply_markup=kb,
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("fc_select_unit:"))
async def cb_fc_select_unit(callback: CallbackQuery):
    arg = callback.data.split(":")[1]
    unit_id = None if arg == "all" else int(arg)
    kb = get_practice_filter_keyboard(prefix="fc_filter", unit_id=unit_id)
    await callback.message.edit_text(
        "🃏 <b>Flashcard toifasini tanlang:</b>\n━━━━━━━━━━━━━━━━━━━━",
        reply_markup=kb,
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("fc_filter:"))
async def cb_start_flashcards(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    parts = callback.data.split(":")
    unit_id = None if parts[1] == "all" else int(parts[1])
    filter_val = None if parts[2] == "all" else parts[2]

    user_id = callback.from_user.id
    words = await get_practice_words(user_id, unit_id=unit_id, status_filter=filter_val, limit=25)
    if not words:
        await callback.answer("Tanlangan toifada so'zlar topilmadi!", show_alert=True)
        return

    random.shuffle(words)
    session_id = str(uuid.uuid4())[:8]
    FLASHCARD_SESSIONS[session_id] = {
        "user_id": user_id,
        "words": words,
        "current_index": 0,
        "known": 0,
        "hard": 0,
    }

    text = _build_card_text(words[0], 0, len(words), revealed=False)
    kb = _build_card_kb(session_id, 0, revealed=False)
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("fc_flip:"))
async def cb_fc_flip(callback: CallbackQuery):
    _, session_id, idx_str = callback.data.split(":")
    idx = int(idx_str)
    session = FLASHCARD_SESSIONS.get(session_id)
    if not session or session["user_id"] != callback.from_user.id:
        await callback.answer("Sessiya eskirgan.", show_alert=True)
        return
    if session["current_index"] != idx:
        await callback.answer("Bu karta allaqachon o'tgan.", show_alert=False)
        return

    word = session["words"][idx]
    text = _build_card_text(word, idx, len(session["words"]), revealed=True)
    kb = _build_card_kb(session_id, idx, revealed=True)
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("fc_tts:"))
async def cb_fc_tts(callback: CallbackQuery):
    _, session_id, idx_str, slow_str = callback.data.split(":")
    idx = int(idx_str)
    slow = slow_str == "1"

    session = FLASHCARD_SESSIONS.get(session_id)
    if not session or session["user_id"] != callback.from_user.id:
        await callback.answer("Sessiya eskirgan.", show_alert=True)
        return

    word = session["words"][idx]
    try:
        audio_fp = await generate_speech_bytes(word["word"], slow=slow)
        voice_file = BufferedInputFile(audio_fp.read(), filename="flashcard.mp3")
        speed_label = "🐢 Sekin" if slow else "🔊 Oddiy"
        uz_pron = f"  •  🗣 <i>[{html.escape(word['uz_pronunciation'])}]</i>" if word.get("uz_pronunciation") else ""
        await callback.message.answer_voice(
            voice=voice_file,
            caption=f"{speed_label}: <b>{html.escape(word['word'])}</b>{uz_pron}",
            parse_mode="HTML",
        )
        await callback.answer()
    except Exception:
        await callback.answer("Audio yuklashda xatolik.", show_alert=True)


@router.callback_query(F.data.startswith("fc_rate:"))
async def cb_fc_rate(callback: CallbackQuery):
    _, session_id, idx_str, known_str = callback.data.split(":")
    idx = int(idx_str)
    is_known = known_str == "1"

    session = FLASHCARD_SESSIONS.get(session_id)
    if not session or session["user_id"] != callback.from_user.id:
        await callback.answer("Sessiya eskirgan.", show_alert=True)
        return
    if session["current_index"] != idx:
        await callback.answer("Bu karta baholangan.", show_alert=False)
        return

    word = session["words"][idx]
    new_status = await record_answer(callback.from_user.id, word["id"], is_correct=is_known)
    if is_known:
        session["known"] += 1
        await callback.answer("✅ Bildim (+1)" + (" 🟢 Yodlandi!" if new_status == "mastered" else ""))
    else:
        session["hard"] += 1
        await callback.answer("🔴 Qiyin so'zlarga qo'shildi!")

    session["current_index"] += 1
    next_idx = session["current_index"]
    total = len(session["words"])
    if next_idx >= total:
        await _finish_flashcards(callback.message, session_id)
        return

    next_word = session["words"][next_idx]
    text = _build_card_text(next_word, next_idx, total, revealed=False)
    kb = _build_card_kb(session_id, next_idx, revealed=False)
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data.startswith("fc_stop:"))
async def cb_fc_stop(callback: CallbackQuery):
    session_id = callback.data.split(":")[1]
    await _finish_flashcards(callback.message, session_id)
    await callback.answer()


async def _finish_flashcards(message: Message, session_id: str):
    session = FLASHCARD_SESSIONS.pop(session_id, None)
    if not session:
        await message.edit_text("Sessiya yakunlangan.")
        return

    total = session["known"] + session["hard"]
    known = session["known"]
    percent = round((known / total * 100), 1) if total > 0 else 0
    bar = progress_bar(known, total, length=10)

    report = (
        f"🃏 <b>FLASHCARD MASHG'ULOTI YAKUNLANDI!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 <b>O'zlashtirish: {percent}%</b>\n"
        f"<code>{bar}</code>\n\n"
        f"• ✅ Bildim: <b>{known} ta</b>\n"
        f"• 🔴 Hali qiyin: <b>{session['hard']} ta</b>\n"
        f"• 📚 Jami ko'rilgan: <b>{total} ta</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💡 <i>'Hali qiyin' deb belgilagan so'zlaringiz har 15 daqiqalik Avto-Eslatmada alohida chiqadi!</i>"
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Yana kartochka ko'rish", callback_data="fc_select_unit:all")],
            [InlineKeyboardButton(text="🔙 Asosiy menyu", callback_data="back_to_menu")],
        ]
    )
    await message.edit_text(report, reply_markup=kb, parse_mode="HTML")

