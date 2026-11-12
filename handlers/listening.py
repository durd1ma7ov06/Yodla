import html
import logging
import random
import uuid
from typing import Dict, Any, List
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
from aiogram.fsm.context import FSMContext

from states.bot_states import ListeningStates
from database.queries import (
    get_user_units,
    get_practice_words,
    get_auto_quiz_distractors,
    record_answer,
)
from keyboards.inline import get_practice_filter_keyboard
from keyboards.reply import get_main_keyboard
from services.tts_service import generate_speech_bytes
from utils.ui_helpers import progress_bar

logger = logging.getLogger(__name__)
router = Router()

LISTENING_SESSIONS: Dict[str, Dict[str, Any]] = {}
_LETTERS = ["A", "B", "C", "D"]


def _truncate_btn(text: str, max_len: int = 44) -> str:
    clean = " ".join((text or "").split())
    if len(clean) <= max_len:
        return clean
    return clean[: max_len - 3].rstrip() + "..."


def _build_listening_kb(options: List[str], session_id: str, question_idx: int) -> InlineKeyboardMarkup:
    rows = []
    for i, opt in enumerate(options):
        rows.append([
            InlineKeyboardButton(
                text=f"{_LETTERS[i]}) {_truncate_btn(opt)}",
                callback_data=f"ls:{session_id}:{question_idx}:{i}",
            )
        ])
    rows.append([
        InlineKeyboardButton(text="🐢 Sekinroq eshitish", callback_data=f"ls_slow:{session_id}:{question_idx}"),
        InlineKeyboardButton(text="🛑 Testni yakunlash", callback_data=f"ls:{session_id}:{question_idx}:stop"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(F.text == "🎧 Eshitib topish (Listening)")
async def start_listening_menu(message: Message):
    user_id = message.from_user.id
    units = await get_user_units(user_id)

    buttons = [[InlineKeyboardButton(text="🌐 Barcha so'zlarimdan", callback_data="listen_select_unit:all")]]
    for u in units:
        buttons.append([
            InlineKeyboardButton(
                text=f"📁 {u['name']} ({u.get('word_count', 0)} ta)",
                callback_data=f"listen_select_unit:{u['id']}",
            )
        ])
    buttons.append([InlineKeyboardButton(text="🔙 Bekor qilish", callback_data="back_to_menu")])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer(
        "🎧 <b>ESHITIB TOPISH (LISTENING TEST):</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🔊 Bot inglizcha so'zning talaffuzini ovozli xabar qilib yuboradi (yozuvsiz).\n"
        "🇺🇿 Siz eshitib, 4 ta variantdan to'g'ri <b>o'zbekcha tarjimasini</b> topasiz!\n\n"
        "Qaysi to'plamdagi so'zlardan mashq qilamiz?",
        reply_markup=kb,
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("unit_listening:"))
async def cb_unit_listening_direct(callback: CallbackQuery):
    unit_id = int(callback.data.split(":")[1])
    kb = get_practice_filter_keyboard(prefix="listen_filter", unit_id=unit_id)
    await callback.message.edit_text(
        "🎧 <b>Listening toifasini tanlang:</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Qaysi so'zlarni eshitib mashq qilamiz?",
        reply_markup=kb,
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("listen_select_unit:"))
async def cb_select_listening_unit(callback: CallbackQuery):
    unit_arg = callback.data.split(":")[1]
    unit_id = None if unit_arg == "all" else int(unit_arg)
    kb = get_practice_filter_keyboard(prefix="listen_filter", unit_id=unit_id)
    await callback.message.edit_text(
        "🎧 <b>Listening toifasini tanlang:</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Qaysi so'zlarni eshitib mashq qilamiz?",
        reply_markup=kb,
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("listen_filter:"))
async def cb_start_listening_session(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    unit_str = parts[1]
    status_filter = parts[2]

    unit_id = None if unit_str == "all" else int(unit_str)
    filter_val = None if status_filter == "all" else status_filter

    user_id = callback.from_user.id
    words = await get_practice_words(user_id, unit_id=unit_id, status_filter=filter_val, limit=20)
    words = [w for w in words if (w.get("word") or "").strip() and (w.get("translation") or "").strip()]

    if not words:
        await callback.answer("Tanlangan toifada so'zlar topilmadi!", show_alert=True)
        return

    random.shuffle(words)
    session_id = str(uuid.uuid4())[:8]
    LISTENING_SESSIONS[session_id] = {
        "user_id": user_id,
        "words": words,
        "current_index": 0,
        "correct": 0,
        "wrong": 0,
        "current_options": [],
        "correct_index": 0,
    }

    await state.set_state(ListeningStates.in_progress)
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.answer("🎧 Ovozli test boshlanmoqda...")
    await send_listening_question(callback.message, session_id)


async def send_listening_question(message: Message, session_id: str):
    session = LISTENING_SESSIONS.get(session_id)
    if not session:
        await message.answer("Listening sessiyasi topilmadi yoki yakunlangan.", reply_markup=get_main_keyboard())
        return

    while True:
        idx = session["current_index"]
        words = session["words"]
        total = len(words)

        if idx >= total:
            await finish_listening(message, session_id)
            return

        current_word = words[idx]
        correct_trans = current_word["translation"].strip()
        distractors = await get_auto_quiz_distractors(
            session["user_id"], current_word["id"], correct_trans, field="translation", count=3
        )
        options = distractors + [correct_trans]
        random.shuffle(options)

        session["current_options"] = options
        session["correct_index"] = options.index(correct_trans)

        try:
            audio_fp = await generate_speech_bytes(current_word["word"], slow=False)
            voice_file = BufferedInputFile(audio_fp.read(), filename="listen_quiz.mp3")
        except Exception as e:
            logger.warning(f"TTS error for '{current_word['word']}': {e}")
            session["current_index"] += 1
            continue

        bar = progress_bar(idx + 1, total, length=8)
        long_options = any(len(" ".join((opt or "").split())) > 44 for opt in options)
        options_block = ""
        if long_options:
            lines = [f"<b>{_LETTERS[i]})</b> {html.escape(opt)}" for i, opt in enumerate(options)]
            options_block = "\n\n" + "\n".join(lines)

        caption = (
            f"🎧 <b>Savol {idx + 1}/{total}</b>  {bar}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🔊 <i>Ovozli xabarni tinglang va eshitgan inglizcha so'zning <b>o'zbekcha tarjimasini</b> tanlang:</i>"
            f"{options_block}\n"
            f"━━━━━━━━━━━━━━━━━━━━"
        )
        kb = _build_listening_kb(options, session_id, idx)
        await message.answer_voice(voice=voice_file, caption=caption, reply_markup=kb, parse_mode="HTML")
        return


@router.callback_query(F.data.startswith("ls_slow:"))
async def cb_listening_slow(callback: CallbackQuery):
    parts = callback.data.split(":")
    session_id = parts[1]
    q_idx = int(parts[2])

    session = LISTENING_SESSIONS.get(session_id)
    if not session or session["user_id"] != callback.from_user.id:
        await callback.answer("Sessiya eskirgan.", show_alert=True)
        return
    if session["current_index"] != q_idx:
        await callback.answer("Bu savol allaqachon o'tgan.", show_alert=False)
        return

    current_word = session["words"][q_idx]
    try:
        audio_fp = await generate_speech_bytes(current_word["word"], slow=True)
        voice_file = BufferedInputFile(audio_fp.read(), filename="listen_slow.mp3")
        await callback.message.answer_voice(
            voice=voice_file,
            caption=f"🐢 <i>Savol {q_idx + 1} — sekinlashtirilgan talaffuz</i>",
            parse_mode="HTML",
        )
        await callback.answer("Sekinlashtirilgan audio yuborildi!")
    except Exception:
        await callback.answer("Audio yuklashda xatolik.", show_alert=True)


@router.callback_query(F.data.startswith("ls:"))
async def cb_handle_listening_answer(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    session_id = parts[1]
    q_idx = int(parts[2])
    ans_str = parts[3]

    session = LISTENING_SESSIONS.get(session_id)
    if not session or session["user_id"] != callback.from_user.id:
        await callback.answer("Sessiya eskirgan.", show_alert=True)
        return

    if session["current_index"] != q_idx:
        await callback.answer("Bu savolga allaqachon javob berilgan!", show_alert=False)
        return

    if ans_str == "stop":
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        await state.clear()
        await finish_listening(callback.message, session_id)
        await callback.answer()
        return

    ans_idx = int(ans_str)
    current_word = session["words"][q_idx]
    is_correct = ans_idx == session["correct_index"]
    chosen_text = session["current_options"][ans_idx]
    correct_trans = current_word["translation"]

    new_status = await record_answer(callback.from_user.id, current_word["id"], is_correct)
    uz_pron = f" <i>[{html.escape(current_word['uz_pronunciation'])}]</i>" if current_word.get("uz_pronunciation") else ""
    trans = f" [<code>{html.escape(current_word['transcription'])}</code>]" if current_word.get("transcription") else ""
    word_line = f"🇬🇧 <b>{html.escape(current_word['word'].upper())}</b>{uz_pron}{trans} — 🇺🇿 <b>{html.escape(correct_trans)}</b>"

    if is_correct:
        session["correct"] += 1
        status_note = " (🟢 Yodlandi!)" if new_status == "mastered" else ""
        caption = f"✅ <b>Barakalla, to'g'ri!{status_note}</b>\n{word_line}"
        await callback.answer(f"✅ To'g'ri! ({current_word['word']})", show_alert=False)
    else:
        session["wrong"] += 1
        caption = (
            f"❌ <b>Noto'g'ri!</b> <i>(Siz: {html.escape(chosen_text)})</i>\n"
            f"✅ {word_line}\n"
            f"🔴 <i>Qiyin so'zlar ro'yxatiga olindi</i>"
        )
        await callback.answer(
            f"❌ Noto'g'ri!\nSo'z: {current_word['word']}\nTarjimasi: {correct_trans}",
            show_alert=True,
        )

    try:
        await callback.message.edit_caption(caption=caption, reply_markup=None, parse_mode="HTML")
    except Exception:
        pass

    session["current_index"] += 1
    if session["current_index"] >= len(session["words"]):
        await state.clear()
    await send_listening_question(callback.message, session_id)


async def finish_listening(message: Message, session_id: str):
    session = LISTENING_SESSIONS.pop(session_id, None)
    if not session:
        return

    total = session["correct"] + session["wrong"]
    correct = session["correct"]
    percent = round((correct / total * 100), 1) if total > 0 else 0

    badge = "🏆 A'lo Quloq va Xotira!" if percent >= 85 else ("👍 Yaxshi Natija!" if percent >= 60 else "💪 Ko'proq Eshitib Mashq Qiling!")
    bar = progress_bar(correct, total, length=10)

    report = (
        f"🎧 <b>LISTENING TEST YAKUNLANDI</b>\n"
        f"{badge}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 <b>Aniqlik darajasi: {percent}%</b>\n"
        f"<code>{bar}</code>\n\n"
        f"• ✅ To'g'ri topilganlar: <b>{correct} ta</b>\n"
        f"• ❌ Xatolar: <b>{session['wrong']} ta</b>\n"
        f"• 🔊 Jami savollar: <b>{total} ta</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💡 <i>Xato qilingan so'zlar 🔴 'Bilmaganlarim' to'plamiga olindi!</i>"
    )

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Yana eshitib topish", callback_data="listen_select_unit:all")],
            [InlineKeyboardButton(text="🔙 Asosiy menyu", callback_data="back_to_menu")],
        ]
    )
    await message.answer(report, reply_markup=kb, parse_mode="HTML")

