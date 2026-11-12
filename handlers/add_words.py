import html
import io
import logging
from aiogram import Router, F, Bot
from aiogram.filters import StateFilter
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from states.bot_states import AddWordStates
from keyboards.reply import get_cancel_keyboard, get_main_keyboard
from keyboards.inline import get_units_keyboard
from services.gemini_service import extract_words_from_image, extract_words_from_text
from database.queries import get_user_units, create_unit, add_words_bulk

logger = logging.getLogger(__name__)
router = Router()

_MAIN_MENU_BTNS = {
    "📸 Rasmdan so'z qo'shish",
    "✍️ Yozib so'z qo'shish",
    "📦 Boshlang'ich to'plamlar",
    "📚 Lug'at to'plamlarim",
    "📊 Mening natijalarim",
    "🃏 Flashcard (Karta)",
    "⚡ Test rejimi (Quiz)",
    "✍️ Imlo mashqi (Spelling)",
    "🎧 Eshitib topish (Listening)",
    "⏰ Avto-Eslatma (Har 15 min)",
    "💡 Qo'llanma va Yordam",
}


def _photo_prompt_text() -> str:
    return (
        "📸 <b>RASMDAN SO'Z QO'SHISH BO'LIMI</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Kitob sahifasi, daftar yoki ekran rasmini yuboring — <b>Sozla AI</b> barcha so'zlarni avtomatik o'qib, tarjima va transkripsiya bilan chiqarib beradi.\n\n"
        "💡 <b>Maslahat:</b>\n"
        "• Rasm tiniq va yorug' bo'lsin;\n"
        "• Sifat buzilmasligi uchun fayl (Document) ko'rinishida ham rasm yuborishingiz mumkin.\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "<i>Iltimos, rasm yuboring (yoki bekor qilish tugmasini bosing):</i>"
    )


def _text_prompt_text() -> str:
    return (
        "✍️ <b>YOZIB SO'Z QO'SHISH BO'LIMI</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Yodlamoqchi bo'lgan so'zlaringizni yozib yuboring — <b>Sozla AI</b> ularning transkripsiyasi, o'zbekcha tarjimasi va misol gaplarini tayyorlaydi.\n\n"
        "📝 <b>Qanday yozish mumkin?</b>\n"
        "• Vergul bilan: <code>abandon, compulsory, reluctant</code>\n"
        "• Qatorma-qator:\n"
        "  <code>resilient</code>\n"
        "  <code>inevitable</code>\n"
        "• Tarjimasi bilan: <code>fragile - mo'rt, sinuvchan</code>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "<i>So'zlarni yozib yuboring:</i>"
    )


@router.message(F.text == "📸 Rasmdan so'z qo'shish")
async def start_add_by_photo(message: Message, state: FSMContext):
    await state.set_state(AddWordStates.waiting_for_photo)
    await message.answer(_photo_prompt_text(), reply_markup=get_cancel_keyboard(), parse_mode="HTML")


@router.message(F.text == "✍️ Yozib so'z qo'shish")
async def start_add_by_text(message: Message, state: FSMContext):
    await state.set_state(AddWordStates.waiting_for_text)
    await message.answer(_text_prompt_text(), reply_markup=get_cancel_keyboard(), parse_mode="HTML")


# Legacy button compatibility (in case user hasn't refreshed keyboard with /start)
@router.message(F.text == "📸 Rasm / ✍️ Matndan so'z qo'shish")
@router.message(F.text == "➕ So'z qo'shish (Rasm / Matn)")
async def start_add_words_legacy(message: Message, state: FSMContext):
    await state.clear()
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📸 Rasmdan qo'shish", callback_data="choose_add_mode:photo"),
                InlineKeyboardButton(text="✍️ Yozib qo'shish", callback_data="choose_add_mode:text"),
            ],
            [InlineKeyboardButton(text="🔙 Bekor qilish", callback_data="back_to_menu")],
        ]
    )
    await message.answer(
        "📥 <b>SO'Z QO'SHISH USULINI TANLANG:</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "<i>Endi rasm va matn orqali qo'shish alohida bo'limlarga ajratilgan (pastki menyuni yangilash uchun /start bosing):</i>",
        reply_markup=kb,
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("choose_add_mode:"))
async def cb_choose_add_mode(callback: CallbackQuery, state: FSMContext):
    mode = callback.data.split(":")[1]
    if mode == "photo":
        await state.set_state(AddWordStates.waiting_for_photo)
        await callback.message.answer(_photo_prompt_text(), reply_markup=get_cancel_keyboard(), parse_mode="HTML")
    else:
        await state.set_state(AddWordStates.waiting_for_text)
        await callback.message.answer(_text_prompt_text(), reply_markup=get_cancel_keyboard(), parse_mode="HTML")
    await callback.answer()


async def _analyze_image_bytes(message: Message, state: FSMContext, image_bytes: bytes):
    wait_msg = await message.answer(
        "🧠 <b>Sozla AI rasmni tahlil qilmoqda...</b>\n"
        "<i>Matn o'qilmoqda va o'zbekcha aniq tarjimalar shakllanmoqda...</i> ⏳",
        parse_mode="HTML",
    )
    try:
        words = await extract_words_from_image(image_bytes)
        if not words:
            await wait_msg.edit_text(
                "❌ Rasmdan so'zlar aniqlanmadi. Iltimos, sifatliroq va aniqroq rasm yuborib ko'ring."
            )
            return

        await handle_extracted_words(message, state, words, wait_msg)
    except Exception as e:
        logger.error(f"Error extracting from photo: {e}", exc_info=True)
        await wait_msg.edit_text(
            f"❌ Xatolik yuz berdi: {html.escape(str(e))}\nIltimos, qaytadan urinib ko'ring."
        )


# --- Photo / Image Document Handlers ---
@router.message(AddWordStates.waiting_for_photo, F.photo)
@router.message(StateFilter(None), F.photo)
async def process_photo_input(message: Message, state: FSMContext, bot: Bot):
    if not message.photo:
        return
    photo = message.photo[-1]
    file = await bot.get_file(photo.file_id)
    file_bytes = io.BytesIO()
    await bot.download_file(file.file_path, file_bytes)
    await _analyze_image_bytes(message, state, file_bytes.getvalue())


@router.message(AddWordStates.waiting_for_photo, F.document)
async def process_image_document(message: Message, state: FSMContext, bot: Bot):
    doc = message.document
    mime = (doc.mime_type or "").lower()
    if not mime.startswith("image/"):
        await message.answer(
            "⚠️ Iltimos, faqat <b>rasm fayli</b> (JPG/PNG) yuboring yoki <b>🔙 Bekor qilish</b> tugmasini bosing.",
            parse_mode="HTML",
        )
        return

    file = await bot.get_file(doc.file_id)
    file_bytes = io.BytesIO()
    await bot.download_file(file.file_path, file_bytes)
    await _analyze_image_bytes(message, state, file_bytes.getvalue())


@router.message(AddWordStates.waiting_for_photo, F.text)
async def process_unexpected_text_in_photo_mode(message: Message, state: FSMContext):
    txt = (message.text or "").strip()
    if txt == "🔙 Bekor qilish":
        await state.clear()
        await message.answer("Amal bekor qilindi.", reply_markup=get_main_keyboard())
        return
    if txt == "✍️ Yozib so'z qo'shish":
        await start_add_by_text(message, state)
        return
    if txt in _MAIN_MENU_BTNS:
        await state.clear()
        await message.answer("Boshqa bo'limga o'tish uchun tugmani qayta bosing.", reply_markup=get_main_keyboard())
        return

    await message.answer(
        "📸 Siz hozir <b>Rasmdan so'z qo'shish</b> bo'limidasiz.\n"
        "Iltimos, rasm yuboring yoki matn kiritish uchun <b>🔙 Bekor qilish</b> tugmasini bosib "
        "<b>✍️ Yozib so'z qo'shish</b> bo'limiga o'ting.",
        reply_markup=get_cancel_keyboard(),
        parse_mode="HTML",
    )


# --- Typed Text Handlers ---
@router.message(AddWordStates.waiting_for_text, F.photo)
async def process_unexpected_photo_in_text_mode(message: Message):
    await message.answer(
        "✍️ Siz hozir <b>Yozib so'z qo'shish</b> bo'limidasiz.\n"
        "Iltimos, so'zlarni matn ko'rinishida yuboring yoki rasm yuklash uchun <b>🔙 Bekor qilish</b> ni bosib "
        "<b>📸 Rasmdan so'z qo'shish</b> bo'limiga o'ting.",
        reply_markup=get_cancel_keyboard(),
        parse_mode="HTML",
    )


@router.message(AddWordStates.waiting_for_text, F.text)
async def process_text_input(message: Message, state: FSMContext):
    text_content = (message.text or "").strip()
    if text_content == "🔙 Bekor qilish":
        await state.clear()
        await message.answer("Amal bekor qilindi.", reply_markup=get_main_keyboard())
        return
    if text_content == "📸 Rasmdan so'z qo'shish":
        await start_add_by_photo(message, state)
        return
    if text_content in _MAIN_MENU_BTNS:
        await state.clear()
        await message.answer("Boshqa bo'limga o'tish uchun tugmani qayta bosing.", reply_markup=get_main_keyboard())
        return

    wait_msg = await message.answer(
        "🧠 <b>Sozla AI yozilgan so'zlarni tahlil qilmoqda...</b> ⏳",
        parse_mode="HTML",
    )

    try:
        words = await extract_words_from_text(text_content)
        if not words:
            await wait_msg.edit_text(
                "❌ Matndan so'zlar ajratib olinmadi. Iltimos, inglizcha so'zlarni aniqroq yozib ko'ring."
            )
            return

        await handle_extracted_words(message, state, words, wait_msg)
    except Exception as e:
        logger.error(f"Error extracting from text: {e}", exc_info=True)
        await wait_msg.edit_text(
            f"❌ Xatolik yuz berdi: {html.escape(str(e))}\nIltimos, qaytadan urinib ko'ring."
        )


# --- Shared Preview & Save to Unit Flow ---
async def handle_extracted_words(message: Message, state: FSMContext, words: list, wait_msg: Message):
    """Formats words preview and presents Unit selection."""
    await state.update_data(extracted_words=words)
    await state.set_state(AddWordStates.waiting_for_unit_choice)

    preview_lines = []
    for i, w in enumerate(words[:12], 1):
        word_str = html.escape(str(w.get("word", "")).upper())
        ipa = str(w.get("transcription", "") or "").strip()
        uz_pron = str(w.get("uz_pronunciation", "") or "").strip()
        pron_parts = []
        if uz_pron:
            pron_parts.append(f"🗣 <i>[{html.escape(uz_pron)}]</i>")
        if ipa:
            pron_parts.append(f"<code>{html.escape(ipa)}</code>")
        trans = (" " + " • ".join(pron_parts)) if pron_parts else ""
        pos = f" <i>({html.escape(str(w.get('part_of_speech', '')))})</i>" if w.get("part_of_speech") else ""
        uz = html.escape(str(w.get("translation", "")))
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

    if not words:
        await state.clear()
        await callback.answer("So'zlar topilmadi, qaytadan urinib ko'ring.", show_alert=True)
        return

    if target == "new":
        await state.set_state(AddWordStates.waiting_for_new_unit_name)
        await callback.message.edit_text(
            "📝 <b>Yangi Unit nomini kiriting:</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "<i>(Masalan: Unit 1, Destination B2, yoki IELTS Vocabulary)</i>",
            parse_mode="HTML",
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
        f"Endi ushbu so'zlarni <b>⚡ Test</b>, <b>🎧 Listening</b> yoki <b>✍️ Imlo mashqi</b> orqali yodlashingiz mumkin!",
        parse_mode="HTML",
    )
    await callback.message.answer("Quyidagi menyudan amallarni tanlang:", reply_markup=get_main_keyboard())
    await callback.answer()


@router.message(AddWordStates.waiting_for_new_unit_name, F.text)
async def process_new_unit_name(message: Message, state: FSMContext):
    unit_name = (message.text or "").strip()
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
        f"🎉 <b>Yangi '{html.escape(unit_name)}' to'plami yaratildi!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"✅ <b>{count} ta so'z</b> muvaffaqiyatli saqlandi.\n\n"
        f"Barcha so'zlar mashqlarga tayyor!",
        reply_markup=get_main_keyboard(),
        parse_mode="HTML",
    )
