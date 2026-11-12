import html
import re
from datetime import datetime
from typing import List, Dict, Any, Optional

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
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
    reset_key_errors,
    is_admin_user,
    get_all_admins,
    add_admin,
    remove_admin,
    get_users_detailed,
    get_all_users_for_export,
    get_user_full_detail,
)
from services.gemini_service import test_api_key_live
from services.export_service import generate_users_excel

router = Router()


class AdminStates(StatesGroup):
    waiting_for_broadcast_msg = State()
    waiting_for_gemini_key = State()
    waiting_for_groq_key = State()
    waiting_for_new_admin_id = State()
    waiting_for_user_search = State()


def mask_key(key: str) -> str:
    k = key.strip()
    if len(k) <= 10:
        return "***"
    return f"{k[:7]}...{k[-5:]}"


def get_admin_main_kb(is_super_admin: bool = False) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text="👥 Foydalanuvchilar jadvali", callback_data="admin_users_page:0"),
            InlineKeyboardButton(text="📄 Excel (.xlsx) yuklash", callback_data="admin_export_users_excel"),
        ],
        [
            InlineKeyboardButton(text="🔍 Foydalanuvchini qidirish", callback_data="admin_search_user_prompt"),
            InlineKeyboardButton(text="🔑 API Kalitlar", callback_data="admin_api_menu"),
        ],
        [
            InlineKeyboardButton(text="📢 Barchaga xabar tarqatish", callback_data="admin_broadcast"),
        ],
    ]
    if is_super_admin:
        buttons.append([
            InlineKeyboardButton(text="👮 Adminlarni boshqarish", callback_data="admin_manage_admins")
        ])
    buttons.append([InlineKeyboardButton(text="🔙 Yopish", callback_data="admin_close")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def get_admin_dashboard_text(user_id: int) -> str:
    stats = await get_global_stats()
    is_super = user_id == ADMIN_ID
    role_str = "Bosh Administrator (Super Admin)" if is_super else "Yordamchi Administrator"

    return (
        "👑 <b>SOZLA AI — BOSHQARUV PANELI</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Sizning maqomingiz:</b> {role_str}\n\n"
        f"📊 <b>ASOSIY STATISTIKA:</b>\n"
        f"• 👥 Jami foydalanuvchilar: <b>{stats['users']} nafar</b>\n"
        f"• ⏰ Avto-Eslatma faollar: <b>{stats.get('active_auto', 0)} nafar</b>\n"
        f"• 📁 Yaratilgan Unitlar: <b>{stats['units']} ta</b>\n"
        f"• 📚 Jami saqlangan so'zlar: <b>{stats['words']} ta</b>\n"
        f"• 🟢 Yodlangan: <b>{stats['mastered']}</b>  |  🔴 Qiyin: <b>{stats['unknown']}</b>\n"
        f"• 🔗 Ulashilgan to'plamlar: <b>{stats.get('total_shares', 0)} ta</b> (📥 {stats.get('total_downloads', 0)} marta olingan)\n"
        f"• 🔑 Faol AI API kalitlar: <b>{stats.get('api_keys', 0)} ta</b>\n"
        f"• 👮 Qo'shimcha adminlar: <b>{stats.get('secondary_admins', 0)} nafar</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "<i>Quyidagi bo'limlardan birini tanlang:</i>"
    )


# --- Entry Points ---
@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext):
    user_id = message.from_user.id
    if not await is_admin_user(user_id):
        return

    await state.clear()
    text = await get_admin_dashboard_text(user_id)
    is_super = user_id == ADMIN_ID
    await message.answer(text, reply_markup=get_admin_main_kb(is_super), parse_mode="HTML")


@router.callback_query(F.data == "admin_back")
async def cb_admin_back(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    if not await is_admin_user(user_id):
        await callback.answer("Ruxsat berilmagan.", show_alert=True)
        return

    await state.clear()
    text = await get_admin_dashboard_text(user_id)
    is_super = user_id == ADMIN_ID
    await callback.message.edit_text(text, reply_markup=get_admin_main_kb(is_super), parse_mode="HTML")
    await callback.answer()


# ==========================================
# 1. FOYDALANUVCHILAR JADVALI (PAGINATED & SEARCH)
# ==========================================
def _build_users_page_text(users: List[Dict[str, Any]], page: int, total_pages: int, total_users: int) -> str:
    lines = [
        f"👥 <b>FOYDALANUVCHILAR JADVALI ({total_users} nafar)</b>",
        f"📄 <b>Sahifa: {page + 1}/{total_pages}</b>",
        "━━━━━━━━━━━━━━━━━━━━",
    ]
    for i, u in enumerate(users, start=page * 10 + 1):
        prem = "⭐ " if u.get("is_premium") else ""
        uname = f"@{u['username']}" if u.get("username") else "yo'q"
        joined = str(u.get("created_at") or "")[:10]
        streak = u.get("streak_count", 0)
        streak_str = f" 🔥{streak}d" if streak > 0 else ""
        auto_ico = "⏰" if u.get("auto_send_enabled", 1) else "🔕"

        lines.append(
            f"<b>{i}. {html.escape(u.get('full_name') or 'Nomsiz')}</b> {prem}{streak_str}\n"
            f"   🆔 <code>{u['user_id']}</code> | {uname}\n"
            f"   📚 {u.get('word_count', 0)} so'z | 📁 {u.get('unit_count', 0)} unit | {auto_ico} | 📅 {joined}"
        )
    lines.append("━━━━━━━━━━━━━━━━━━━━")
    return "\n\n".join(lines)


def _build_users_pagination_kb(page: int, total_pages: int) -> InlineKeyboardMarkup:
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="◀️ Oldingi", callback_data=f"admin_users_page:{page - 1}"))
    nav_row.append(InlineKeyboardButton(text=f"• {page + 1}/{total_pages} •", callback_data="admin_noop"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton(text="Keyingi ▶️", callback_data=f"admin_users_page:{page + 1}"))

    return InlineKeyboardMarkup(
        inline_keyboard=[
            nav_row,
            [
                InlineKeyboardButton(text="📄 Excel (.xlsx) yuklash", callback_data="admin_export_users_excel"),
                InlineKeyboardButton(text="🔍 Qidirish", callback_data="admin_search_user_prompt"),
            ],
            [InlineKeyboardButton(text="🔙 Admin panelga", callback_data="admin_back")],
        ]
    )


@router.callback_query(F.data.startswith("admin_users_page:"))
async def cb_admin_users_page(callback: CallbackQuery):
    if not await is_admin_user(callback.from_user.id):
        return

    page = int(callback.data.split(":")[1])
    limit = 10
    offset = page * limit

    users, total_count = await get_users_detailed(limit=limit, offset=offset)
    total_pages = max(1, (total_count + limit - 1) // limit)
    page = min(page, total_pages - 1)

    text = _build_users_page_text(users, page, total_pages, total_count)
    kb = _build_users_pagination_kb(page, total_pages)
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "admin_users_list")
async def cb_admin_users_list_alias(callback: CallbackQuery):
    await cb_admin_users_page(callback)


# ==========================================
# 2. EXCEL (.XLSX) EKSPORT QILISH
# ==========================================
@router.callback_query(F.data == "admin_export_users_excel")
async def cb_export_users_excel(callback: CallbackQuery):
    if not await is_admin_user(callback.from_user.id):
        return

    await callback.answer("📊 Excel jadvali tayyorlanmoqda...")
    wait_msg = await callback.message.answer("⏳ <b>Foydalanuvchilar ma'lumotlari Excel (.xlsx) fayliga yozilmoqda...</b>", parse_mode="HTML")

    try:
        users = await get_all_users_for_export()
        excel_buf = await generate_users_excel(users)
        date_str = datetime.now().strftime("%Y_%m_%d")
        filename = f"Foydalanuvchilar_SozlaAI_{date_str}.xlsx"

        doc = BufferedInputFile(excel_buf.read(), filename=filename)
        await callback.message.answer_document(
            document=doc,
            caption=(
                f"📊 <b>Foydalanuvchilar to'liq jadvali (Excel .xlsx)</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"👥 Jami: <b>{len(users)} nafar</b> a'zo\n"
                f"<i>ID, so'zlar soni, o'zlashtirish, streak va boshqa barcha statistikalar jamlangan!</i>"
            ),
            parse_mode="HTML",
        )
        await wait_msg.delete()
    except Exception as e:
        await wait_msg.edit_text(f"❌ Excel generatsiyasida xatolik: {e}")


# ==========================================
# 3. FOYDALANUVCHINI QIDIRISH (SEARCH)
# ==========================================
@router.callback_query(F.data == "admin_search_user_prompt")
async def cb_search_user_prompt(callback: CallbackQuery, state: FSMContext):
    if not await is_admin_user(callback.from_user.id):
        return

    await state.set_state(AdminStates.waiting_for_user_search)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Bekor qilish", callback_data="admin_users_page:0")]])
    await callback.message.edit_text(
        "🔍 <b>Foydalanuvchini qidirish:</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Foydalanuvchining <b>Telegram ID</b> raqamini, <b>@username</b>ini yoki <b>ism-familiyasi</b>ni yozib yuboring:",
        reply_markup=kb,
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminStates.waiting_for_user_search, F.text)
async def process_user_search_input(message: Message, state: FSMContext):
    if not await is_admin_user(message.from_user.id):
        return

    query_str = message.text.strip().replace("@", "")
    await state.clear()

    # Search in database
    users, total_count = await get_users_detailed(limit=10, offset=0, search=query_str)
    if not users:
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔍 Qaytadan qidirish", callback_data="admin_search_user_prompt")],
                [InlineKeyboardButton(text="🔙 Ro'yxatga qaytish", callback_data="admin_users_page:0")],
            ]
        )
        await message.answer(f"❌ <code>{html.escape(query_str)}</code> bo'yicha hech kim topilmadi.", reply_markup=kb, parse_mode="HTML")
        return

    lines = [
        f"🔍 <b>QIDIRUV NATIJALARI ('{html.escape(query_str)}' — {total_count} ta):</b>",
        "━━━━━━━━━━━━━━━━━━━━",
    ]
    for i, u in enumerate(users, 1):
        prem = "⭐ " if u.get("is_premium") else ""
        uname = f"@{u['username']}" if u.get("username") else "yo'q"
        streak = u.get("streak_count", 0)
        lines.append(
            f"<b>{i}. {html.escape(u.get('full_name') or 'Nomsiz')}</b> {prem}\n"
            f"   🆔 <code>{u['user_id']}</code> | {uname}\n"
            f"   📚 {u.get('word_count', 0)} ta so'z (🟢 {u.get('mastered_count', 0)} / 🔴 {u.get('unknown_count', 0)})\n"
            f"   📁 {u.get('unit_count', 0)} unit | 🔥 {streak} kun streak | 📅 {str(u.get('created_at') or '')[:10]}"
        )
    lines.append("━━━━━━━━━━━━━━━━━━━━")

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔍 Yana qidirish", callback_data="admin_search_user_prompt")],
            [InlineKeyboardButton(text="👥 Barcha foydalanuvchilar", callback_data="admin_users_page:0")],
            [InlineKeyboardButton(text="🔙 Admin panelga", callback_data="admin_back")],
        ]
    )
    await message.answer("\n\n".join(lines), reply_markup=kb, parse_mode="HTML")


# ==========================================
# 4. ADMINLARNI BOSHQARISH (SUPER ADMIN ONLY)
# ==========================================
@router.callback_query(F.data == "admin_manage_admins")
async def cb_manage_admins(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id != ADMIN_ID:
        await callback.answer("Faqat Bosh Administrator adminlarni boshqara oladi!", show_alert=True)
        return

    admins = await get_all_admins()
    lines = [
        "👮 <b>ADMINISTRATORLARNI BOSHQARISH</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        f"👑 <b>Bosh Admin (Super Admin):</b> <code>{ADMIN_ID}</code>",
        "",
        f"👥 <b>Yordamchi Adminlar ({len(admins)} nafar):</b>",
    ]

    if not admins:
        lines.append("   <i>Hozircha qo'shimcha adminlar yo'q.</i>")
    else:
        for i, a in enumerate(admins, 1):
            un = f"@{a['username']}" if a.get("username") else "yo'q"
            lines.append(f"   {i}. <b>{html.escape(a.get('full_name') or 'Admin')}</b> (<code>{a['user_id']}</code> | {un})")

    lines.append("━━━━━━━━━━━━━━━━━━━━")

    buttons = [
        [InlineKeyboardButton(text="➕ Admin qo'shish", callback_data="admin_add_prompt")],
    ]
    if admins:
        buttons.append([InlineKeyboardButton(text="🗑 Adminni o'chirish", callback_data="admin_remove_menu")])
    buttons.append([InlineKeyboardButton(text="🔙 Admin panelga", callback_data="admin_back")])

    await callback.message.edit_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "admin_add_prompt")
async def cb_admin_add_prompt(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return

    await state.set_state(AdminStates.waiting_for_new_admin_id)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Bekor qilish", callback_data="admin_manage_admins")]])
    await callback.message.edit_text(
        "➕ <b>Yangi Admin qo'shish:</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Admin qilmoqchi bo'lgan foydalanuvchining <b>Telegram ID</b> raqamini yozing:\n\n"
        "<i>(Eslatma: Bu foydalanuvchi botga kamida bir marta /start bosgan bo'lishi kerak)</i>",
        reply_markup=kb,
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminStates.waiting_for_new_admin_id, F.text)
async def process_new_admin_input(message: Message, state: FSMContext, bot: Bot):
    if message.from_user.id != ADMIN_ID:
        return

    text = message.text.strip()
    if not text.isdigit():
        await message.answer("❌ Iltimos, faqat raqamlardan iborat <b>Telegram ID</b> kiriting (masalan: <code>123456789</code>).", parse_mode="HTML")
        return

    new_admin_id = int(text)
    if new_admin_id == ADMIN_ID:
        await message.answer("ℹ️ Bu raqam allaqachon Bosh Administrator hisoblanadi.")
        await state.clear()
        return

    ok = await add_admin(user_id=new_admin_id, added_by=ADMIN_ID)
    await state.clear()

    if ok:
        try:
            await bot.send_message(
                chat_id=new_admin_id,
                text="🎉 <b>Tabriklaymiz!</b> Siz <b>Sozla AI</b> botiga Administrator etib tayinlandingiz.\nBoshqaruv uchun /admin buyrug'ini yuboring.",
                parse_mode="HTML",
            )
        except Exception:
            pass
        await message.answer(f"✅ Foydalanuvchi <code>{new_admin_id}</code> muvaffaqiyatli <b>Admin</b> etib qo'shildi!", parse_mode="HTML")
    else:
        await message.answer("ℹ️ Bu foydalanuvchi allaqachon Adminlar ro'yxatida mavjud.")


@router.callback_query(F.data == "admin_remove_menu")
async def cb_admin_remove_menu(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return

    admins = await get_all_admins()
    if not admins:
        await callback.answer("O'chirish uchun adminlar yo'q.", show_alert=True)
        return

    buttons = []
    for a in admins:
        name_str = a.get("full_name") or f"Admin #{a['user_id']}"
        buttons.append([
            InlineKeyboardButton(
                text=f"🗑 O'chirish: {name_str[:25]} ({a['user_id']})",
                callback_data=f"act_rm_admin:{a['user_id']}",
            )
        ])
    buttons.append([InlineKeyboardButton(text="🔙 Adminlar ro'yxatiga", callback_data="admin_manage_admins")])

    await callback.message.edit_text(
        "🗑 <b>Qaysi adminni vakolatini bekor qilmoqchisiz?</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("act_rm_admin:"))
async def cb_act_remove_admin(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return

    target_id = int(callback.data.split(":")[1])
    await remove_admin(target_id)
    await callback.answer(f"Admin #{target_id} muvaffaqiyatli o'chirildi!", show_alert=True)
    await cb_manage_admins(callback)


# ==========================================
# 5. API KALITLAR BOSHQARUVI
# ==========================================
async def build_api_menu_text() -> str:
    keys = await get_api_keys()
    gemini_keys = [k for k in keys if k["provider"] == "gemini"]
    groq_keys = [k for k in keys if k["provider"] == "groq"]

    lines = [
        "🔑 <b>API KALITLARNI BOSHQARISH MARKAZI</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        "<i>Kalitlar avtomatik almashib (Rotation) ishlaydi. Biri tugasa, keyingisiga o'tadi.</i>\n",
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
                InlineKeyboardButton(text="➕ Groq qo'shish", callback_data="add_api:groq"),
            ],
            [
                InlineKeyboardButton(text="⚡ Kalitlarni test qilish", callback_data="test_all_apis"),
                InlineKeyboardButton(text="🗑 Kalitni o'chirish", callback_data="delete_api_menu"),
            ],
            [InlineKeyboardButton(text="🔙 Admin Panelga", callback_data="admin_back")],
        ]
    )


@router.callback_query(F.data == "admin_api_menu")
async def cb_admin_api_menu(callback: CallbackQuery, state: FSMContext):
    if not await is_admin_user(callback.from_user.id):
        return
    await state.clear()
    text = await build_api_menu_text()
    await callback.message.edit_text(text, reply_markup=get_api_menu_kb(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("add_api:"))
async def cb_add_api_prompt(callback: CallbackQuery, state: FSMContext):
    if not await is_admin_user(callback.from_user.id):
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
        f"<i>Bot ularni darhol jonli tekshirib, bazaga qo'shadi!</i>",
        reply_markup=kb,
        parse_mode="HTML",
    )
    await callback.answer()


async def _process_new_api_keys(message: Message, state: FSMContext, provider: str):
    raw = message.text.strip()
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
        + "\n".join(results)
        + "\n━━━━━━━━━━━━━━━━━━━━"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔑 API Menyusiga qaytish", callback_data="admin_api_menu")]])
    await wait_msg.edit_text(report, reply_markup=kb, parse_mode="HTML")


@router.message(AdminStates.waiting_for_gemini_key, F.text)
async def process_gemini_key_input(message: Message, state: FSMContext):
    if not await is_admin_user(message.from_user.id):
        return
    await _process_new_api_keys(message, state, "gemini")


@router.message(AdminStates.waiting_for_groq_key, F.text)
async def process_groq_key_input(message: Message, state: FSMContext):
    if not await is_admin_user(message.from_user.id):
        return
    await _process_new_api_keys(message, state, "groq")


@router.callback_query(F.data == "test_all_apis")
async def cb_test_all_apis(callback: CallbackQuery):
    if not await is_admin_user(callback.from_user.id):
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
        + "\n\n".join(results)
        + "\n━━━━━━━━━━━━━━━━━━━━"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Orqaga", callback_data="admin_api_menu")]])
    await callback.message.edit_text(report, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "delete_api_menu")
async def cb_delete_api_menu(callback: CallbackQuery):
    if not await is_admin_user(callback.from_user.id):
        return
    keys = await get_api_keys()
    if not keys:
        await callback.answer("O'chirish uchun kalit yo'q.", show_alert=True)
        return

    buttons = []
    for k in keys:
        buttons.append([
            InlineKeyboardButton(
                text=f"🗑 #{k['id']} {k['provider'].upper()} ({mask_key(k['api_key'])})",
                callback_data=f"del_api_id:{k['id']}",
            )
        ])
    buttons.append([InlineKeyboardButton(text="🔙 Orqaga", callback_data="admin_api_menu")])

    await callback.message.edit_text(
        "🗑 <b>Qaysi API kalitni o'chirmoqchisiz?</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("del_api_id:"))
async def cb_delete_api_confirm(callback: CallbackQuery):
    if not await is_admin_user(callback.from_user.id):
        return
    key_id = int(callback.data.split(":")[1])
    await delete_api_key(key_id)
    await callback.answer(f"Kalit #{key_id} o'chirildi!", show_alert=True)
    text = await build_api_menu_text()
    await callback.message.edit_text(text, reply_markup=get_api_menu_kb(), parse_mode="HTML")


# ==========================================
# 6. BARCHAGA XABAR TARQATISH (BROADCAST)
# ==========================================
@router.callback_query(F.data == "admin_broadcast")
async def cb_admin_broadcast(callback: CallbackQuery, state: FSMContext):
    if not await is_admin_user(callback.from_user.id):
        return

    await state.set_state(AdminStates.waiting_for_broadcast_msg)
    await callback.message.edit_text(
        "📢 <b>Xabar tarqatish:</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Barcha foydalanuvchilarga yubormoqchi bo'lgan xabaringizni yozing (matn, rasm yoki video bo'lishi mumkin):\n\n"
        "<i>Bekor qilish uchun /cancel deb yozing.</i>",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminStates.waiting_for_broadcast_msg)
async def process_broadcast(message: Message, state: FSMContext, bot: Bot):
    if not await is_admin_user(message.from_user.id):
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
        parse_mode="HTML",
    )


@router.callback_query(F.data == "admin_noop")
async def cb_admin_noop(callback: CallbackQuery):
    await callback.answer()


@router.callback_query(F.data == "admin_close")
async def cb_admin_close(callback: CallbackQuery):
    await callback.message.delete()
