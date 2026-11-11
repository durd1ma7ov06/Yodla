from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from config import ADMIN_ID
from database.queries import get_global_stats, get_all_users

router = Router()

class AdminStates(StatesGroup):
    waiting_for_broadcast_msg = State()

@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    stats = await get_global_stats()
    text = (
        "👑 <b>SOZLA AI — BOSH ADMIN PANELI</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"👥 Jami foydalanuvchilar: <b>{stats['users']} nafar</b>\n"
        f"📁 Yaratilgan Unitlar: <b>{stats['units']} ta</b>\n"
        f"📚 Jami saqlangan so'zlar: <b>{stats['words']} ta</b>\n"
        f"🟢 O'zlashtirilgan so'zlar: <b>{stats['mastered']} ta</b>\n"
        f"🔴 Qiyin deb topilgan so'zlar: <b>{stats['unknown']} ta</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "<i>Quyidagi amallardan birini tanlang:</i>"
    )

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👥 Foydalanuvchilar ro'yxati", callback_data="admin_users_list")],
            [InlineKeyboardButton(text="📢 Barchaga xabar tarqatish", callback_data="admin_broadcast")],
            [InlineKeyboardButton(text="🔙 Yopish", callback_data="admin_close")]
        ]
    )
    await message.answer(text, reply_markup=kb, parse_mode="HTML")

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
    
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Orqaga", callback_data="admin_back")]
        ]
    )
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "admin_back")
async def cb_admin_back(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return

    stats = await get_global_stats()
    text = (
        "👑 <b>SOZLA AI — BOSH ADMIN PANELI</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"👥 Jami foydalanuvchilar: <b>{stats['users']} nafar</b>\n"
        f"📁 Yaratilgan Unitlar: <b>{stats['units']} ta</b>\n"
        f"📚 Jami saqlangan so'zlar: <b>{stats['words']} ta</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        "<i>Quyidagi amallardan birini tanlang:</i>"
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👥 Foydalanuvchilar ro'yxati", callback_data="admin_users_list")],
            [InlineKeyboardButton(text="📢 Barchaga xabar tarqatish", callback_data="admin_broadcast")],
            [InlineKeyboardButton(text="🔙 Yopish", callback_data="admin_close")]
        ]
    )
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

