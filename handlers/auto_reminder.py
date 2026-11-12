import asyncio
import html
import logging
import random
from typing import Dict, Any, List
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
from aiogram.exceptions import TelegramForbiddenError

from database.queries import (
    get_user_auto_settings,
    update_user_auto_settings,
    get_users_due_for_auto_word,
    get_next_word_for_auto_send,
    mark_auto_word_sent,
    get_auto_quiz_distractors,
    create_auto_challenge,
    get_auto_challenge,
    mark_auto_challenge_answered,
    record_answer,
    get_word_by_id,
)
from services.tts_service import generate_speech_bytes

logger = logging.getLogger(__name__)
router = Router()

_LETTERS = ["A", "B", "C", "D"]


def _status_badge(status: str, incorrect_count: int = 0) -> str:
    if status == "unknown":
        return "🔴 Xato qilingan so'z"
    if incorrect_count > 0 and status != "mastered":
        return "🟠 Qiyin so'z (Oldin xato qilingan)"
    if status == "mastered":
        return "🟢 Yodlangan (Takror)"
    return "🟡 O'rganilayotgan so'z"


def _truncate_btn(text: str, max_len: int = 44) -> str:
    clean = " ".join((text or "").split())
    if len(clean) <= max_len:
        return clean
    return clean[: max_len - 3].rstrip() + "..."


def _build_challenge_text(
    word: Dict[str, Any],
    interval_min: int,
    direction: str,
    options: List[str],
) -> str:
    status = word.get("status", "learning")
    incorrect_count = word.get("incorrect_count", 0)
    badge = _status_badge(status, incorrect_count)
    unit_name = html.escape(word.get("unit_name") or "Umumiy")
    pos = f" <i>({html.escape(word['part_of_speech'])})</i>" if word.get("part_of_speech") else ""

    if direction == "en_to_uz":
        dir_label = "🇬🇧 ➔ 🇺🇿"
        trans = f" [<code>{html.escape(word['transcription'])}</code>]" if word.get("transcription") else ""
        prompt_block = (
            f"🇬🇧 <b>{html.escape(word['word'].upper())}</b>{pos}{trans}\n\n"
            f"❓ <i>Ushbu inglizcha so'zning o'zbekcha tarjimasini toping:</i>"
        )
    else:
        dir_label = "🇺🇿 ➔ 🇬🇧"
        prompt_block = (
            f"🇺🇿 <b>{html.escape(word['translation'])}</b>{pos}\n\n"
            f"❓ <i>Ushbu ma'noga mos inglizcha so'zni toping:</i>"
        )

    long_options = any(len(" ".join((opt or "").split())) > 44 for opt in options)
    options_block = ""
    if long_options:
        lines = [f"<b>{_LETTERS[i]})</b> {html.escape(opt)}" for i, opt in enumerate(options)]
        options_block = "\n\n" + "\n".join(lines)

    return (
        f"⏰ <b>{interval_min} DAQIQALIK SO'Z TESTI</b>  ({dir_label})\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📁 <b>Unit:</b> {unit_name}  •  {badge}\n\n"
        f"{prompt_block}{options_block}\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )


def _build_challenge_kb(
    challenge_id: int,
    word_id: int,
    direction: str,
    options: List[str],
) -> InlineKeyboardMarkup:
    rows = []
    for i, opt in enumerate(options):
        rows.append([
            InlineKeyboardButton(
                text=f"{_LETTERS[i]}) {_truncate_btn(opt)}",
                callback_data=f"aq:{challenge_id}:{i}",
            )
        ])

    action_row = []
    if direction == "en_to_uz":
        action_row.append(InlineKeyboardButton(text="🔊 Talaffuz", callback_data=f"auto_tts:{word_id}"))
    action_row.append(InlineKeyboardButton(text="👁 Javobni ko'rish", callback_data=f"aq_reveal:{challenge_id}"))
    rows.append(action_row)
    rows.append([InlineKeyboardButton(text="⚙️ Eslatma sozlamalari", callback_data="auto_settings_open")])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def _build_revealed_text(
    word: Dict[str, Any],
    result_banner: str,
) -> str:
    unit_name = html.escape(word.get("unit_name") or "Umumiy")
    pos = f" <i>({html.escape(word['part_of_speech'])})</i>" if word.get("part_of_speech") else ""
    trans = f" [<code>{html.escape(word['transcription'])}</code>]" if word.get("transcription") else ""

    text = (
        f"{result_banner}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📁 <b>Unit:</b> {unit_name}\n\n"
        f"🇬🇧 <b>{html.escape(word['word'].upper())}</b>{pos}{trans}\n"
        f"🇺🇿 <b>Tarjimasi:</b> {html.escape(word['translation'])}"
    )
    if word.get("example_en"):
        text += f"\n\n💬 <i>\"{html.escape(word['example_en'])}\"</i>"
        if word.get("example_uz"):
            text += f"\n🇺🇿 <i>({html.escape(word['example_uz'])})</i>"
    text += "\n━━━━━━━━━━━━━━━━━━━━"
    return text


def _build_post_answer_kb(word_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔊 Talaffuz", callback_data=f"auto_tts:{word_id}"),
                InlineKeyboardButton(text="⚡ Yana bitta savol", callback_data="auto_send_now"),
            ],
            [InlineKeyboardButton(text="⚙️ Eslatma sozlamalari", callback_data="auto_settings_open")],
        ]
    )


async def send_auto_word_to_user(bot: Bot, user_id: int, interval_min: int = 15) -> bool:
    word = await get_next_word_for_auto_send(user_id)
    if not word:
        return False

    has_en = bool((word.get("word") or "").strip())
    has_uz = bool((word.get("translation") or "").strip())
    if not has_en or not has_uz:
        return False

    direction = random.choice(["en_to_uz", "uz_to_en"])
    if direction == "en_to_uz":
        correct_value = word["translation"].strip()
        distractors = await get_auto_quiz_distractors(
            user_id, word["id"], correct_value, field="translation", count=3
        )
    else:
        correct_value = word["word"].strip()
        distractors = await get_auto_quiz_distractors(
            user_id, word["id"], correct_value, field="word", count=3
        )

    options = distractors + [correct_value]
    random.shuffle(options)
    correct_index = options.index(correct_value)

    challenge_id = await create_auto_challenge(
        user_id=user_id,
        word_id=word["id"],
        direction=direction,
        options=options,
        correct_index=correct_index,
    )

    text = _build_challenge_text(word, interval_min, direction, options)
    kb = _build_challenge_kb(challenge_id, word["id"], direction, options)

    try:
        await bot.send_message(chat_id=user_id, text=text, reply_markup=kb, parse_mode="HTML")
        await mark_auto_word_sent(user_id, word["id"])
        return True
    except TelegramForbiddenError:
        logger.info(f"User {user_id} blocked the bot. Disabling auto_send.")
        await update_user_auto_settings(user_id, enabled=0)
        return False
    except Exception as e:
        logger.warning(f"Failed to send auto word to {user_id}: {e}")
        return False


async def auto_word_scheduler(bot: Bot):
    """Background loop checking every 60 seconds for users due for their vocabulary drip."""
    logger.info("⏰ Avto-Eslatma (Har 15 minutlik so'z yuborish) tizimi ishga tushdi.")
    while True:
        try:
            await asyncio.sleep(60)
            due_users = await get_users_due_for_auto_word()
            for u in due_users:
                await send_auto_word_to_user(bot, u["user_id"], u["interval"])
                await asyncio.sleep(0.2)
        except asyncio.CancelledError:
            logger.info("Avto-Eslatma scheduler to'xtatildi.")
            break
        except Exception as e:
            logger.error(f"Auto scheduler error: {e}", exc_info=True)
            await asyncio.sleep(10)


# --- Settings Menu ---
def _format_interval_label(minutes: int) -> str:
    if minutes < 60:
        return f"Har {minutes} daqiqada"
    hours = minutes // 60
    return f"Har {hours} soatda"


async def _build_settings_ui(user_id: int):
    settings = await get_user_auto_settings(user_id)
    enabled = bool(settings["enabled"])
    interval = settings["interval"]

    status_str = "🟢 Yoqilgan (Faol)" if enabled else "🔴 O'chirilgan"
    interval_str = _format_interval_label(interval)

    text = (
        "⏰ <b>AVTO-ESLATMA SOZLAMALARI (SMART TEST)</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Bot belgilangan vaqt oralig'ida sizning <b>🔴 xato qilgan / qiyin so'zlaringizdan</b> "
        "tasodifiy birini tanlab, faqat <b>bitta tomonini</b> yuboradi:\n"
        "• 🇬🇧 Inglizcha kelsa — 🇺🇿 o'zbekchasini topasiz;\n"
        "• 🇺🇿 O'zbekcha kelsa — 🇬🇧 inglizchasini topasiz.\n\n"
        f"• <b>Holati:</b> {status_str}\n"
        f"• <b>Yuborish tezligi:</b> <b>{interval_str}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "<i>Sozlash uchun tugmalardan foydalaning:</i>"
    )

    toggle_text = "🔴 O'chirib qo'yish" if enabled else "🟢 Yoqish"
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=toggle_text, callback_data="auto_toggle")],
            [
                InlineKeyboardButton(text=f"{'✅ ' if interval == 15 else ''}15 min", callback_data="auto_int:15"),
                InlineKeyboardButton(text=f"{'✅ ' if interval == 30 else ''}30 min", callback_data="auto_int:30"),
                InlineKeyboardButton(text=f"{'✅ ' if interval == 60 else ''}1 soat", callback_data="auto_int:60"),
                InlineKeyboardButton(text=f"{'✅ ' if interval == 180 else ''}3 soat", callback_data="auto_int:180"),
            ],
            [InlineKeyboardButton(text="⚡ Hozir bitta savol yuborish", callback_data="auto_send_now")],
            [InlineKeyboardButton(text="🔙 Menyuga qaytish", callback_data="back_to_menu")],
        ]
    )
    return text, kb


@router.message(F.text == "⏰ Avto-Eslatma (Har 15 min)")
async def cmd_auto_settings(message: Message):
    text, kb = await _build_settings_ui(message.from_user.id)
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "auto_settings_open")
async def cb_open_auto_settings(callback: CallbackQuery):
    text, kb = await _build_settings_ui(callback.from_user.id)
    await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "auto_toggle")
async def cb_toggle_auto(callback: CallbackQuery):
    user_id = callback.from_user.id
    settings = await get_user_auto_settings(user_id)
    new_val = 0 if settings["enabled"] else 1
    await update_user_auto_settings(user_id, enabled=new_val)

    text, kb = await _build_settings_ui(user_id)
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer("Sozlama yangilandi!")


@router.callback_query(F.data.startswith("auto_int:"))
async def cb_set_interval(callback: CallbackQuery):
    user_id = callback.from_user.id
    interval = int(callback.data.split(":")[1])
    await update_user_auto_settings(user_id, enabled=1, interval=interval)

    text, kb = await _build_settings_ui(user_id)
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer(f"Vaqt oralig'i {_format_interval_label(interval)} qilib belgilandi!")


@router.callback_query(F.data == "auto_send_now")
async def cb_auto_send_now(callback: CallbackQuery, bot: Bot):
    user_id = callback.from_user.id
    settings = await get_user_auto_settings(user_id)
    sent = await send_auto_word_to_user(bot, user_id, settings["interval"])
    if not sent:
        await callback.answer("Sizda hali so'zlar yo'q! Avval rasm yoki matn orqali so'z qo'shing.", show_alert=True)
    else:
        await callback.answer("Savol yuborildi!")


# --- Challenge Answer & Reveal Handlers ---
@router.callback_query(F.data.startswith("aq:"))
async def cb_auto_quiz_answer(callback: CallbackQuery):
    parts = callback.data.split(":")
    challenge_id = int(parts[1])
    chosen_idx = int(parts[2])
    user_id = callback.from_user.id

    challenge = await get_auto_challenge(challenge_id, user_id)
    if not challenge:
        await callback.answer("Bu savol topilmadi yoki muddati o'tgan.", show_alert=True)
        return
    if challenge["answered"]:
        await callback.answer("Bu savolga allaqachon javob bergansiz!", show_alert=False)
        return

    word = await get_word_by_id(challenge["word_id"], user_id)
    if not word:
        await callback.answer("So'z o'chirilgan.", show_alert=True)
        return

    await mark_auto_challenge_answered(challenge_id)
    is_correct = chosen_idx == challenge["correct_index"]
    new_status = await record_answer(user_id, word["id"], is_correct=is_correct)

    options = challenge["options"]
    chosen_text = options[chosen_idx] if 0 <= chosen_idx < len(options) else ""
    correct_text = options[challenge["correct_index"]]

    if is_correct:
        status_msg = "🟢 <i>So'z yodlanganlar safiga o'tdi!</i>" if new_status == "mastered" else "🟡 <i>Bilimingiz mustahkamlandi (+1).</i>"
        banner = f"✅ <b>BARAKALLA, TO'G'RI TOPDINGIZ!</b>\n{status_msg}"
        await callback.answer("✅ To'g'ri! (+1)", show_alert=False)
    else:
        banner = (
            f"❌ <b>XATO JAVOB!</b>\n"
            f"• Siz tanladingiz: <s>{html.escape(chosen_text)}</s>\n"
            f"• To'g'ri javob: <b>{html.escape(correct_text)}</b>\n"
            f"🔴 <i>Qiyin so'zlar ro'yxatida qoldi — yana eslataman!</i>"
        )
        await callback.answer(f"❌ Noto'g'ri! To'g'ri javob: {correct_text}", show_alert=True)

    revealed = _build_revealed_text(word, banner)
    await callback.message.edit_text(
        revealed,
        reply_markup=_build_post_answer_kb(word["id"]),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("aq_reveal:"))
async def cb_auto_quiz_reveal(callback: CallbackQuery):
    challenge_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id

    challenge = await get_auto_challenge(challenge_id, user_id)
    if not challenge:
        await callback.answer("Savol topilmadi.", show_alert=True)
        return
    if challenge["answered"]:
        await callback.answer("Bu savol allaqachon ochilgan!", show_alert=False)
        return

    word = await get_word_by_id(challenge["word_id"], user_id)
    if not word:
        await callback.answer("So'z topilmadi.", show_alert=True)
        return

    await mark_auto_challenge_answered(challenge_id)
    await record_answer(user_id, word["id"], is_correct=False)

    banner = "👁 <b>JAVOB KO'RSATILDI</b>\n🔴 <i>Qiyin / bilmagan so'zlar ro'yxatiga olindi.</i>"
    revealed = _build_revealed_text(word, banner)
    await callback.message.edit_text(
        revealed,
        reply_markup=_build_post_answer_kb(word["id"]),
        parse_mode="HTML",
    )
    await callback.answer("So'z 🔴 Qiyin so'zlar ro'yxatiga qo'shildi.")


# --- Backward-compatible Legacy Card Handlers & TTS ---
@router.callback_query(F.data.startswith("auto_know:"))
async def cb_auto_know(callback: CallbackQuery):
    word_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    new_status = await record_answer(user_id, word_id, is_correct=True)

    note = "✅ <b>Barakalla!</b> " + ("So'z 🟢 Yodlanganlar safiga o'tdi!" if new_status == "mastered" else "Bilimingiz oshdi (+1).")
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⚡ Yana bitta savol", callback_data="auto_send_now")]])
    await callback.message.edit_text(callback.message.html_text + f"\n\n{note}", reply_markup=kb, parse_mode="HTML")
    await callback.answer("Zo'r! (+1)")


@router.callback_query(F.data.startswith("auto_dont_know:"))
async def cb_auto_dont_know(callback: CallbackQuery):
    word_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    await record_answer(user_id, word_id, is_correct=False)

    note = "🔴 <b>Qiyin so'zlar ro'yxatiga qo'shildi.</b> Tez orada yana eslataman!"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⚡ Yana bitta savol", callback_data="auto_send_now")]])
    await callback.message.edit_text(callback.message.html_text + f"\n\n{note}", reply_markup=kb, parse_mode="HTML")
    await callback.answer("Saqlandi! Tez orada qayta yuboraman.")


@router.callback_query(F.data.startswith("auto_tts:"))
async def cb_auto_tts(callback: CallbackQuery):
    word_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    word = await get_word_by_id(word_id, user_id)
    if not word:
        await callback.answer("So'z topilmadi.", show_alert=True)
        return

    try:
        audio_fp = await generate_speech_bytes(word["word"])
        voice_file = BufferedInputFile(audio_fp.read(), filename="pronunciation.mp3")
        await callback.message.answer_voice(
            voice=voice_file,
            caption=f"🔊 <b>{html.escape(word['word'])}</b> — <code>{html.escape(word.get('transcription') or '')}</code>",
            parse_mode="HTML",
        )
        await callback.answer()
    except Exception:
        await callback.answer("Audio yuklashda xatolik.", show_alert=True)
