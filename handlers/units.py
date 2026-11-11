from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from database.queries import get_user_units, get_unit, delete_unit, get_words_by_unit
from keyboards.inline import get_unit_details_keyboard, get_units_keyboard
from keyboards.reply import get_main_keyboard

router = Router()

@router.message(F.text == "📚 Lug'at to'plamlarim")
@router.message(F.text == "📚 Mening Unitlarim")
async def show_user_units(message: Message):
    user_id = message.from_user.id
    units = await get_user_units(user_id)
    
    if not units:
        await message.answer(
            "📭 <b>Sizda hali hech qanday Unit mavjud emas.</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "Yangi lug'at qo'shish uchun <b>📸 Rasm / ✍️ Matndan so'z qo'shish</b> tugmasini bosing!",
            reply_markup=get_main_keyboard(),
            parse_mode="HTML"
        )
        return

    text = (
        "📚 <b>SIZNING LUG'AT TO'PLAMLARINGIZ:</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "<i>Kerakli Unit ustiga bosing:</i>"
    )
    keyboard = get_units_keyboard(units, action_prefix="view_unit")
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")

@router.callback_query(F.data == "back_to_units")
async def cb_back_to_units(callback: CallbackQuery):
    user_id = callback.from_user.id
    units = await get_user_units(user_id)
    text = (
        "📚 <b>SIZNING LUG'AT TO'PLAMLARINGIZ:</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "<i>Kerakli Unit ustiga bosing:</i>"
    )
    keyboard = get_units_keyboard(units, action_prefix="view_unit")
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data.startswith("view_unit:"))
async def cb_view_unit_details(callback: CallbackQuery):
    unit_id_str = callback.data.split(":")[1]
    if unit_id_str == "new":
        await callback.message.edit_text(
            "➕ Yangi Unit ochish uchun avval <b>📸 Rasm / ✍️ Matndan so'z qo'shish</b> tugmasini bosib so'zlarni yuboring.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_to_units")]])
        )
        await callback.answer()
        return

    unit_id = int(unit_id_str)
    user_id = callback.from_user.id
    unit = await get_unit(unit_id, user_id)
    if not unit:
        await callback.answer("Unit topilmadi!", show_alert=True)
        return

    words = await get_words_by_unit(unit_id, user_id)
    total = len(words)
    mastered = sum(1 for w in words if w.get("status") == "mastered")
    unknown = sum(1 for w in words if w.get("status") == "unknown")
    learning = total - mastered - unknown

    text = (
        f"📁 <b>To'plam: {unit['name']}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 <b>Statistika:</b>\n"
        f"• 📚 Jami so'zlar: <b>{total} ta</b>\n"
        f"• 🟢 Yodlangan: <b>{mastered} ta</b>\n"
        f"• 🟡 O'rganilmoqda: <b>{learning} ta</b>\n"
        f"• 🔴 Qiyin so'zlar: <b>{unknown} ta</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>Quyidagi amallardan birini tanlang:</i>"
    )
    await callback.message.edit_text(text, reply_markup=get_unit_details_keyboard(unit_id), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data.startswith("unit_words:"))
async def cb_show_unit_words(callback: CallbackQuery):
    unit_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    words = await get_words_by_unit(unit_id, user_id)

    if not words:
        await callback.answer("Bu Unitda so'zlar yo'q!", show_alert=True)
        return

    lines = []
    for i, w in enumerate(words, 1):
        status = w.get("status", "learning")
        emoji = "🟢" if status == "mastered" else ("🔴" if status == "unknown" else "🟡")
        trans = f" <code>{w['transcription']}</code>" if w.get("transcription") else ""
        lines.append(f"{emoji} <b>{i}. {w['word'].upper()}</b>{trans}\n   🇺🇿 {w['translation']}")

    full_text = f"📖 <b>Unit so'zlari ({len(words)} ta):</b>\n━━━━━━━━━━━━━━━━━━━━\n" + "\n\n".join(lines)
    if len(full_text) > 4000:
        full_text = full_text[:3900] + "\n\n<i>... (matn qisqartirildi)</i>"

    back_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Unitga qaytish", callback_data=f"view_unit:{unit_id}")]
        ]
    )
    await callback.message.edit_text(full_text, reply_markup=back_kb, parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data.startswith("unit_delete:"))
async def cb_delete_unit(callback: CallbackQuery):
    unit_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    
    await delete_unit(unit_id, user_id)
    await callback.answer("Unit muvaffaqiyatli o'chirildi!", show_alert=True)
    
    units = await get_user_units(user_id)
    if units:
        text = "📚 <b>Sizning Unitlaringiz ro'yxati:</b>\n<i>Kerakli Unit ustiga bosing:</i>"
        keyboard = get_units_keyboard(units, action_prefix="view_unit")
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    else:
        await callback.message.edit_text("📭 Hozirda hech qanday Unit qolmadi.")
