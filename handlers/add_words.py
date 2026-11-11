import io
import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from states.bot_states import AddWordStates
from keyboards.reply import get_cancel_keyboard, get_main_keyboard
from keyboards.inline import get_units_keyboard
from services.gemini_service import extract_words_from_image, extract_words_from_text
from database.queries import get_user_units, create_unit, add_words_bulk

logger = logging.getLogger(__name__)
router = Router()

@router.message(F.text == "📸 Rasm / ✍️ Matndan so'z qo'shish")
@router.message(F.text == "➕ So'z qo'shish (Rasm / Matn)")
async def start_add_words(message: Message, state: FSMContext):
    await state.set_state(AddWordStates.waiting_for_input)
    text = (
        "📥 <b>Yangi lug'at qo'shish:</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Siz 2 xil usulda so'z kiritishingiz mumkin:\n\n"
        "1️⃣ 📸 <b>Rasm yuborish</b>: Kitobdagi Unit sahifasini yoki lug'at ro'yxatini rasmga olib tashlang.\n"
        "2️⃣ ✍️ <b>Matn yozish</b>: So'zlarni vergul bilan yoki har qatorda bittadan yozib yuboring:\n"
        "   <i>Masalan: abandon, compulsory, reluctant, deliberate</i>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "<i>Rasmni yoki matnni yuboring:</i>"
    )
    await message.answer(text, reply_markup=get_cancel_keyboard(), parse_mode="HTML")

@router.message(AddWordStates.waiting_for_input, F.photo)
@router.message(F.photo)
async def process_photo_input(message: Message, state: FSMContext, bot: Bot):
    if not message.photo:
        return
        
    wait_msg = await message.answer(
        "🧠 <b>Sozla AI rasmni tahlil qilmoqda...</b>\n"
        "<i>Matn o'qilmoqda va o'zbekcha aniq tarjimalar shakllanmoqda...</i> ⏳",
        parse_mode="HTML"
    )
    
    try:
        photo = message.photo[-1]
        file = await bot.get_file(photo.file_id)
        file_bytes = io.BytesIO()
        await bot.download_file(file.file_path, file_bytes)
        
        words = await extract_words_from_image(file_bytes.getvalue())
        if not words:
            await wait_msg.edit_text("❌ Rasmdan so'zlar aniqlanmadi. Iltimos, sifatliroq va aniqroq rasm yuborib ko'ring.")
            return

        await handle_extracted_words(message, state, words, wait_msg)
    except Exception as e:
        logger.error(f"Error extracting from photo: {e}", exc_info=True)
        await wait_msg.edit_text(f"❌ Xatolik yuz berdi: {str(e)}\nIltimos, qaytadan urinib ko'ring yoki .env faylida GEMINI_API_KEY to'g'ri kiritilganini tekshiring.")

@router.message(AddWordStates.waiting_for_input, F.text)
async def process_text_input(message: Message, state: FSMContext):
    text_content = message.text.strip()
    if text_content == "🔙 Bekor qilish":
        await state.clear()
        await message.answer("Amal bekor qilindi.", reply_markup=get_main_keyboard())
        return

    wait_msg = await message.answer(
        "🧠 <b>Sozla AI matnni tahlil qilmoqda...</b> ⏳",
        parse_mode="HTML"
    )
    
    try:
        words = await extract_words_from_text(text_content)
        if not words:
            await wait_msg.edit_text("❌ Matndan so'zlar ajratib olinmadi. Iltimos, boshqa matn kiritib ko'ring.")
            return

        await handle_extracted_words(message, state, words, wait_msg)
    except Exception as e:
        logger.error(f"Error extracting from text: {e}", exc_info=True)
        await wait_msg.edit_text(f"❌ Xatolik yuz berdi: {str(e)}\nIltimos, qaytadan urinib ko'ring.")

async def handle_extracted_words(message: Message, state: FSMContext, words: list, wait_msg: Message):
    """Formats words preview and presents Unit selection."""
    await state.update_data(extracted_words=words)
    await state.set_state(AddWordStates.waiting_for_unit_choice)
    
    preview_lines = []
    for i, w in enumerate(words[:12], 1):
        word_str = w.get("word", "").upper()
        trans = f" <code>{w.get('transcription', '')}</code>" if w.get("transcription") else ""
        pos = f" <i>({w.get('part_of_speech', '')})</i>" if w.get("part_of_speech") else ""
        uz = w.get("translation", "")
        preview_lines.append(f"<b>{i}. {word_str}</b>{pos}{trans}\n   🇺🇿 {uz}")
        
    more_count = len(words) - 12
    more_text = f"\n<i>... va yana {more_count} ta so'z</i>" if more_count > 0 else ""
    
    summary_text = (
        f"✅ <b>Jami {len(words)} ta so'z muvaffaqiyatli aniqlandi!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        + "\n\n".join(preview_lines) + more_text + "\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📁 <b>Ushbu so'zlarni qaysi Unit to'plamiga saqlamoqchisiz?</b>"
    )
    
    user_id = message.from_user.id
    units = await get_user_units(user_id)
    keyboard = get_units_keyboard(units, action_prefix="save_to_unit")
    
    await wait_msg.edit_text(summary_text, reply_markup=keyboard, parse_mode="HTML")

@router.callback_query(AddWordStates.waiting_for_unit_choice, F.data.startswith("save_to_unit:"))
async def cb_save_to_unit(callback: CallbackQuery, state: FSMContext):
    target = callback.data.split(":")[1]
    user_id = callback.from_user.id
    data = await state.get_data()
    words = data.get("extracted_words", [])

    if target == "new":
        await state.set_state(AddWordStates.waiting_for_new_unit_name)
        await callback.message.edit_text(
            "📝 <b>Yangi Unit nomini kiriting:</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "<i>(Masalan: Unit 1, Destination B2, yoki IELTS Vocabulary)</i>",
            parse_mode="HTML"
        )
        await callback.answer()
        return

    unit_id = int(target)
    count = await add_words_bulk(unit_id, user_id, words)
    await state.clear()
    
    await callback.message.edit_text(
        f"🎉 <b>Muvaffaqiyatli saqlandi!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"✅ <b>{count} ta so'z</b> to'plamingizga qo'shildi.\n\n"
        f"Endi ushbu so'zlarni <b>⚡ Test</b> yoki <b>✍️ Imlo mashqi</b> orqali yodlashni boshlashingiz mumkin!",
        parse_mode="HTML"
    )
    await callback.message.answer("Quyidagi menyudan amallarni tanlang:", reply_markup=get_main_keyboard())
    await callback.answer()

@router.message(AddWordStates.waiting_for_new_unit_name, F.text)
async def process_new_unit_name(message: Message, state: FSMContext):
    unit_name = message.text.strip()
    if unit_name == "🔙 Bekor qilish":
        await state.clear()
        await message.answer("Bekor qilindi.", reply_markup=get_main_keyboard())
        return

    user_id = message.from_user.id
    data = await state.get_data()
    words = data.get("extracted_words", [])

    unit_id = await create_unit(user_id, unit_name)
    count = await add_words_bulk(unit_id, user_id, words)
    await state.clear()

    await message.answer(
        f"🎉 <b>Yangi '{unit_name}' to'plami yaratildi!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"✅ <b>{count} ta so'z</b> muvaffaqiyatli saqlandi.\n\n"
        f"Barcha so'zlar mashqlarga tayyor!",
        reply_markup=get_main_keyboard(),
        parse_mode="HTML"
    )
