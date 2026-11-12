import asyncio
import logging
from typing import Dict, Any
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
from aiogram.exceptions import TelegramForbiddenError

from database.queries import (
    get_user_auto_settings,
    update_user_auto_settings,
    get_users_due_for_auto_word,
    get_next_word_for_auto_send,
    mark_auto_word_sent,
    record_answer,
    get_word_by_id,
)
from services.tts_service import generate_speech_bytes

logger = logging.getLogger(__name__)
router = Router()

def _build_auto_card_text(word: Dict[str, Any], interval_min: int) -> str:
    status = word.get("status", "learning")
    badge = "🔴 Bilmagan so'zingiz" if status == "unknown" else ("🟢 Yodlangan (Takror)" if status == "mastered" else "🟡 O'rganilayotgan so'z")
    unit_name = word.get("unit_name") or "Umumiy"
    pos = f" <i>({word['part_of_speech']})</i>" if word.get("part_of_speech") else ""
    trans = f" [<code>{word['transcription']}</code>]" if word.get("transcription") else ""
    
    text = (
        f"⏰ <b>{interval_min} DAQIQALIK SO'Z ESLATMASI</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📁 <b>Unit:</b> {unit_name}  •  {badge}\n\n"
        f"🇬🇧 <b>{word['word'].upper()}</b>{pos}{trans}\n"
        f"🇺🇿 <b>Tarjimasi:</b> {word['translation']}\n"
    )
    if word.get("example_en"):
        text += f"\n💬 <i>\"{word['example_en']}\"</i>"
        if word.get("example_uz"):
            text += f"\n🇺🇿 <i>({word['example_uz']})</i>"
    text += "\n━━━━━━━━━━━━━━━━━━━━\n<i>Ushbu so'zni eslab qoldingizmi?</i>"
    return text

def _build_auto_card_kb(word_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Bilaman / Yodladim", callback_data=f"auto_know:{word_id}"),
                InlineKeyboardButton(text="❌ Hali qiyin", callback_data=f"auto_dont_know:{word_id}")
            ],
            [
                InlineKeyboardButton(text="🔊 Talaffuz", callback_data=f"auto_tts:{word_id}"),
                InlineKeyboardButton(text="⚙️ Eslatma sozlamalari", callback_data="auto_settings_open")
            ]
        ]
    )

async def send_auto_word_to_user(bot: Bot, user_id: int, interval_min: int = 15) -> bool:
    word = await get_next_word_for_auto_send(user_id)
    if not word:
        return False

    text = _build_auto_card_text(word, interval_min)
    kb = _build_auto_card_kb(word["id"])
    
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
                await asyncio.sleep(0.2) # gentle rate limit protection
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
        "⏰ <b>AVTO-ESLATMA SOZLAMALARI (SMART DRIP)</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Bot belgilangan vaqt oralig'ida sizga avtomatik ravishda <b>1 ta lug'at so'zi</b> "
        "(ayniqsa 🔴 qiyin so'zlaringizdan) yuborib turadi. Bu so'zlarni kun davomida unutmaysiz!\n\n"
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
            [InlineKeyboardButton(text="⚡ Hozir bitta so'z yuborish", callback_data="auto_send_now")],
            [InlineKeyboardButton(text="🔙 Menyuga qaytish", callback_data="back_to_menu")]
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
        await callback.answer("So'z yuborildi!")

# --- Notification Interactive Feedback ---
@router.callback_query(F.data.startswith("auto_know:"))
async def cb_auto_know(callback: CallbackQuery):
    word_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    new_status = await record_answer(user_id, word_id, is_correct=True)
    
    note = "✅ <b>Barakalla!</b> " + ("So'z 🟢 Yodlanganlar safiga o'tdi!" if new_status == "mastered" else "Bilimingiz oshdi (+1).")
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⚡ Yana bitta so'z", callback_data="auto_send_now")]])
    await callback.message.edit_text(callback.message.html_text + f"\n\n{note}", reply_markup=kb, parse_mode="HTML")
    await callback.answer("Zo'r! (+1)")

@router.callback_query(F.data.startswith("auto_dont_know:"))
async def cb_auto_dont_know(callback: CallbackQuery):
    word_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    await record_answer(user_id, word_id, is_correct=False)
    
    note = "🔴 <b>Qiyin so'zlar ro'yxatiga qo'shildi.</b> Tez orada yana eslataman!"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⚡ Yana bitta so'z", callback_data="auto_send_now")]])
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
        await callback.message.answer_voice(voice=voice_file, caption=f"🔊 <b>{word['word']}</b> — <code>{word.get('transcription', '')}</code>", parse_mode="HTML")
        await callback.answer()
    except Exception:
        await callback.answer("Audio yuklashda xatolik.", show_alert=True)
