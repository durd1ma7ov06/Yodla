import html
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from utils.starter_packs import STARTER_PACKS, get_starter_pack_by_id
from database.queries import get_user_units, create_unit, add_words_bulk

router = Router()


async def _build_packs_menu(user_id: int):
    existing_units = await get_user_units(user_id)
    existing_names = {u["name"].strip().lower() for u in existing_units}

    buttons = []
    for pack in STARTER_PACKS:
        added_mark = " ✅" if pack["unit_name"].strip().lower() in existing_names else ""
        buttons.append([
            InlineKeyboardButton(
                text=f"{pack['title']} ({len(pack['words'])} ta){added_mark}",
                callback_data=f"sp_preview:{pack['id']}",
            )
        ])
    buttons.append([InlineKeyboardButton(text="🔙 Menyuga qaytish", callback_data="back_to_menu")])

    text = (
        "📦 <b>BOSHLANG'ICH TALABALAR UCHUN TAYYOR TO'PLAMLAR (A0–A1)</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Ingliz tilini noldan o'rganish uchun eng muhim so'zlar to'plamlari.\n"
        "Har bir so'zda <b>🇺🇿 o'zbekcha o'qilishi</b>, tarjimasi, misol gapi va 🔊 audiosi bor!\n\n"
        "<i>Ko'rish va 1 bosishda qo'shish uchun to'plamni tanlang:</i>"
    )
    return text, InlineKeyboardMarkup(inline_keyboard=buttons)


@router.message(F.text == "📦 Boshlang'ich to'plamlar")
async def cmd_starter_packs(message: Message):
    text, kb = await _build_packs_menu(message.from_user.id)
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "open_starter_packs")
async def cb_open_starter_packs(callback: CallbackQuery):
    text, kb = await _build_packs_menu(callback.from_user.id)
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("sp_preview:"))
async def cb_preview_starter_pack(callback: CallbackQuery):
    pack_id = callback.data.split(":")[1]
    pack = get_starter_pack_by_id(pack_id)
    if not pack:
        await callback.answer("To'plam topilmadi.", show_alert=True)
        return

    existing_units = await get_user_units(callback.from_user.id)
    existing_map = {u["name"].strip().lower(): u["id"] for u in existing_units}
    already_unit_id = existing_map.get(pack["unit_name"].strip().lower())

    sample_lines = []
    for i, w in enumerate(pack["words"][:6], 1):
        sample_lines.append(
            f"{i}. <b>{html.escape(w['word'])}</b> "
            f"🗣 <i>[{html.escape(w['uz_pronunciation'])}]</i> — {html.escape(w['translation'])}"
        )

    status_note = "\n✅ <i>Siz bu to'plamni allaqachon qo'shgansiz!</i>" if already_unit_id else ""
    text = (
        f"📦 <b>{html.escape(pack['title'])}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{html.escape(pack['description'])}\n"
        f"📚 Jami so'zlar: <b>{len(pack['words'])} ta</b>{status_note}\n\n"
        f"<b>Namuna so'zlar:</b>\n" + "\n".join(sample_lines) + "\n<i>... va yana boshqalar</i>\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )

    buttons = []
    if already_unit_id:
        buttons.append([
            InlineKeyboardButton(text="📁 Unitni ochish", callback_data=f"view_unit:{already_unit_id}"),
            InlineKeyboardButton(text="🃏 Flashcard boshlash", callback_data=f"unit_flashcards:{already_unit_id}"),
        ])
        buttons.append([InlineKeyboardButton(text="➕ Qaytadan nusxa qo'shish", callback_data=f"sp_import:{pack_id}")])
    else:
        buttons.append([InlineKeyboardButton(text="📥 1 bosishda Unit qilib qo'shish", callback_data=f"sp_import:{pack_id}")])
    buttons.append([InlineKeyboardButton(text="🔙 Boshqa to'plamlar", callback_data="open_starter_packs")])

    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("sp_import:"))
async def cb_import_starter_pack(callback: CallbackQuery):
    pack_id = callback.data.split(":")[1]
    pack = get_starter_pack_by_id(pack_id)
    if not pack:
        await callback.answer("To'plam topilmadi.", show_alert=True)
        return

    user_id = callback.from_user.id
    unit_id = await create_unit(user_id, pack["unit_name"])
    count = await add_words_bulk(unit_id, user_id, pack["words"])

    text = (
        f"🎉 <b>'{html.escape(pack['unit_name'])}' QO'SHILDI!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"✅ <b>{count} ta boshlang'ich so'z</b> bazangizga saqlandi.\n"
        f"Endi darhol o'rganishni boshlashingiz mumkin:"
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🃏 Flashcard (Karta)", callback_data=f"fc_filter:{unit_id}:all"),
                InlineKeyboardButton(text="⚡ Test (Quiz)", callback_data=f"quiz_filter:{unit_id}:all"),
            ],
            [
                InlineKeyboardButton(text="🎧 Eshitib topish", callback_data=f"listen_filter:{unit_id}:all"),
                InlineKeyboardButton(text="📄 Word (.docx)", callback_data=f"unit_export_word:{unit_id}"),
            ],
            [InlineKeyboardButton(text="📦 Yana to'plam qo'shish", callback_data="open_starter_packs")],
            [InlineKeyboardButton(text="🔙 Asosiy menyu", callback_data="back_to_menu")],
        ]
    )
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer(f"✅ {count} ta so'z qo'shildi!")
