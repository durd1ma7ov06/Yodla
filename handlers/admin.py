from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from config import ADMIN_ID
from database.queries import (
    get_global_stats,
    get_all_users,
    get_api_keys,
    add_api_key,
    delete_api_key,
    reset_key_errors
)
from services.gemini_service import test_api_key_live

router = Router()

class AdminStates(StatesGroup):
    waiting_for_broadcast_msg = State()
    waiting_for_gemini_key = State()
    waiting_for_groq_key = State()

def mask_key(key: str) -> str:
    k = key.strip()
    if len(k) <= 10:
        return "***"
    return f"{k[:7]}...{k[-5:]}"

def get_admin_main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔑 API Kalitlar (Gemini / Groq)", callback_data="admin_api_menu")],
            [InlineKeyboardButton(text="👥 Foydalanuvchilar ro'yxati", callback_data="admin_users_list")],
            [InlineKeyboardButton(text="📢 Barchaga xabar tarqatish", callback_data="admin_broadcast")],
            [InlineKeyboardButton(text="🔙 Yopish", callback_data="admin_close")]
        ]
    )

async def get_admin_dashboard_text() -> str:
    stats = await get_global_stats()
    return (
        "👑 <b>SOZLA AI — BOSH ADMIN PANELI</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"👥 Jami foydalanuvchilar: <b>{stats['users']} nafar</b>\n"
        f"📁 Yaratilgan Unitlar: <b>{stats['units']} ta</b>\n"
        f"📚 Jami saqlangan so'zlar: <b>{stats['words']} ta</b>\n"
        f"🔑 Faol API kalitlar: <b>{stats.get('api_keys', 0)} ta</b>\n"
        f"🟢 O'zlashtirilgan so'zlar: <b>{stats['mastered']} ta</b>\n"
        f"🔴 Qiyin deb topilgan so'zlar: <b>{stats['unknown']} ta</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "<i>Quyidagi amallardan birini tanlang:</i>"
    )

@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.clear()
    text = await get_admin_dashboard_text()
    await message.answer(text, reply_markup=get_admin_main_kb(), parse_mode="HTML")

@router.callback_query(F.data == "admin_back")
async def cb_admin_back(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    await state.clear()
    text = await get_admin_dashboard_text()
    await callback.message.edit_text(text, reply_markup=get_admin_main_kb(), parse_mode="HTML")
    await callback.answer()

# --- API Keys Management ---
async def build_api_menu_text() -> str:
    keys = await get_api_keys()
    gemini_keys = [k for k in keys if k["provider"] == "gemini"]
    groq_keys = [k for k in keys if k["provider"] == "groq"]

    lines = [
        "🔑 <b>API KALITLARNI BOSHQARISH MARKAZI</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        "<i>Kalitlar avtomatik almashib (Rotation) ishlaydi. Birining limiti tugasa, keyingisiga o'tadi.</i>\n"
    ]

    lines.append(f"🧠 <b>GEMINI API KALITLARI ({len(gemini_keys)} ta):</b>")
    if not gemini_keys:
        lines.append("   <i>Kalit qo'shilmagan</i>")
    else:
        for k in gemini_keys:
            lines.append(f"   • <b>#{k['id']}</b> <code>{mask_key(k['api_key'])}</code> | 📊 Ishladi: {k['usage_count']} | ⚠️ Xato: {k['error_count']}")

    lines.append(f"\n⚡ <b>GROQ API KALITLARI ({len(groq_keys)} ta):</b>")
    if not groq_keys:
        lines.append("   <i>Kalit qo'shilmagan</i>")
    else:
        for k in groq_keys:
            lines.append(f"   • <b>#{k['id']}</b> <code>{mask_key(k['api_key'])}</code> | 📊 Ishladi: {k['usage_count']} | ⚠️ Xato: {k['error_count']}")

    lines.append("━━━━━━━━━━━━━━━━━━━━")
    return "\n".join(lines)

def get_api_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="➕ Gemini qo'shish", callback_data="add_api:gemini"),
                InlineKeyboardButton(text="➕ Groq qo'shish", callback_data="add_api:groq")
            ],
            [
                InlineKeyboardButton(text="⚡ Kalitlarni test qilish", callback_data="test_all_apis"),
                InlineKeyboardButton(text="🗑 Kalitni o'chirish", callback_data="delete_api_menu")
            ],
            [InlineKeyboardButton(text="🔙 Admin Panelga", callback_data="admin_back")]
        ]
    )

@router.callback_query(F.data == "admin_api_menu")
async def cb_admin_api_menu(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    await state.clear()
    text = await build_api_menu_text()
    await callback.message.edit_text(text, reply_markup=get_api_menu_kb(), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data.startswith("add_api:"))
async def cb_add_api_prompt(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    provider = callback.data.split(":")[1]
    
    if provider == "gemini":
        await state.set_state(AdminStates.waiting_for_gemini_key)
        p_name = "Google Gemini"
    else:
        await state.set_state(AdminStates.waiting_for_groq_key)
        p_name = "Groq"

    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Bekor qilish", callback_data="admin_api_menu")]])
    await callback.message.edit_text(
        f"➕ <b>Yangi {p_name} API kalitini qo'shish:</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Kalitni (yoki bir nechta kalitlarni qatorma-qator) shu yerga yozib yuboring.\n\n"
        f"<i>Men har bir kalitni jonli tekshirib, bazaga qo'shib qo'yaman!</i>",
        reply_markup=kb,
        parse_mode="HTML"
    )
    await callback.answer()

async def _process_new_api_keys(message: Message, state: FSMContext, provider: str):
    raw = message.text.strip()
    # Support splitting by newline or comma or space
    candidates = [x.strip() for x in raw.replace(",", "\n").split() if len(x.strip()) > 10]
    
    if not candidates:
        await message.answer("❌ To'g'ri API kalit kiritilmadi. Qaytadan yuboring yoki bekor qiling.")
        return

    wait_msg = await message.answer(f"⏳ <b>{len(candidates)} ta {provider.upper()} kaliti tekshirilmoqda...</b>", parse_mode="HTML")
    
    results = []
    for key in candidates:
        is_ok, status_msg = await test_api_key_live(provider, key)
        added = await add_api_key(provider, key)
        if added:
            icon = "✅" if is_ok else "⚠️"
            results.append(f"{icon} <code>{mask_key(key)}</code> — Qo'shildi ({status_msg})")
        else:
            results.append(f"ℹ️ <code>{mask_key(key)}</code> — Allaqachon bazada bor ({status_msg})")

    await state.clear()
    report = (
        f"🔑 <b>{provider.upper()} KALITLAR NATIJASI:</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        + "\n".join(results) +
        f"\n━━━━━━━━━━━━━━━━━━━━"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔑 API Menyusiga qaytish", callback_data="admin_api_menu")]])
    await wait_msg.edit_text(report, reply_markup=kb, parse_mode="HTML")

@router.message(AdminStates.waiting_for_gemini_key, F.text)
async def process_gemini_key_input(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await _process_new_api_keys(message, state, "gemini")

@router.message(AdminStates.waiting_for_groq_key, F.text)
async def process_groq_key_input(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await _process_new_api_keys(message, state, "groq")

@router.callback_query(F.data == "test_all_apis")
async def cb_test_all_apis(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
        
    keys = await get_api_keys()
    if not keys:
        await callback.answer("Tekshirish uchun kalitlar yo'q!", show_alert=True)
        return

    await callback.message.edit_text("⏳ <b>Barcha API kalitlar jonli tekshirilmoqda...</b>", parse_mode="HTML")
    
    results = []
    for k in keys:
        is_ok, msg = await test_api_key_live(k["provider"], k["api_key"])
        if is_ok:
            await reset_key_errors(k["id"])
        icon = "🟢" if is_ok else "🔴"
        results.append(f"{icon} <b>#{k['id']} [{k['provider'].upper()}]</b> <code>{mask_key(k['api_key'])}</code>\n    └ {msg}")

    report = (
        "⚡ <b>JONLI API DIAGNOSTIKA NATIJASI:</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        + "\n\n".join(results) +
        "\n━━━━━━━━━━━━━━━━━━━━"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Orqaga", callback_data="admin_api_menu")]])
    await callback.message.edit_text(report, reply_markup=kb, parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "delete_api_menu")
async def cb_delete_api_menu(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    keys = await get_api_keys()
    if not keys:
        await callback.answer("O'chirish uchun kalit yo'q.", show_alert=True)
        return

    buttons = []
    for k in keys:
        buttons.append([
            InlineKeyboardButton(
                text=f"🗑 O'chirish: #{k['id']} {k['provider'].upper()} ({mask_key(k['api_key'])})",
                callback_data=f"del_api_id:{k['id']}"
            )
        ])
    buttons.append([InlineKeyboardButton(text="🔙 Orqaga", callback_data="admin_api_menu")])

    await callback.message.edit_text(
        "🗑 <b>Qaysi API kalitni o'chirmoqchisiz?</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("del_api_id:"))
async def cb_delete_api_confirm(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    key_id = int(callback.data.split(":")[1])
    await delete_api_key(key_id)
    await callback.answer(f"Kalit #{key_id} o'chirildi!", show_alert=True)
    text = await build_api_menu_text()
    await callback.message.edit_text(text, reply_markup=get_api_menu_kb(), parse_mode="HTML")

# --- Users List & Broadcast ---
@router.callback_query(F.data == "admin_users_list")
async def cb_admin_users(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return

    users = await get_all_users()
    if not users:
        await callback.answer("Hozircha foydalanuvchilar yo'q.", show_alert=True)
        return

    lines = []
    for i, u in enumerate(users[:25], 1):
        uname = f"@{u['username']}" if u['username'] else "yo'q"
        prem = "⭐" if u.get("is_premium") else ""
        lines.append(f"<b>{i}. {u['full_name']}</b> {prem}\n   🆔 <code>{u['user_id']}</code> | 🔗 {uname} | 🌐 {u.get('language_code', 'uz')}")

    text = f"👥 <b>Foydalanuvchilar ro'yxati (Jami {len(users)} nafar):</b>\n━━━━━━━━━━━━━━━━━━━━\n" + "\n\n".join(lines)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Orqaga", callback_data="admin_back")]])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "admin_broadcast")
async def cb_admin_broadcast(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return

    await state.set_state(AdminStates.waiting_for_broadcast_msg)
    await callback.message.edit_text(
        "📢 <b>Xabar tarqatish:</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Barcha foydalanuvchilarga yubormoqchi bo'lgan xabaringizni yozing (matn, rasm yoki video bo'lishi mumkin):\n\n"
        "<i>Bekor qilish uchun /cancel deb yozing.</i>",
        parse_mode="HTML"
    )
    await callback.answer()

@router.message(AdminStates.waiting_for_broadcast_msg)
async def process_broadcast(message: Message, state: FSMContext, bot: Bot):
    if message.from_user.id != ADMIN_ID:
        return

    if message.text == "/cancel":
        await state.clear()
        await message.answer("Xabar tarqatish bekor qilindi.")
        return

    users = await get_all_users()
    sent = 0
    failed = 0

    progress_msg = await message.answer(f"⏳ Xabar tarqatilmoqda (0/{len(users)})...")

    for u in users:
        try:
            await bot.copy_message(chat_id=u["user_id"], from_chat_id=message.chat.id, message_id=message.message_id)
            sent += 1
        except Exception:
            failed += 1

    await state.clear()
    await progress_msg.edit_text(
        f"✅ <b>Xabar tarqatildi!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"• Yuborildi: <b>{sent} kishiga</b>\n"
        f"• Yetib bormadi (bloklagan): <b>{failed} kishi</b>",
        parse_mode="HTML"
    )

@router.callback_query(F.data == "admin_close")
async def cb_admin_close(callback: CallbackQuery):
    await callback.message.delete()
