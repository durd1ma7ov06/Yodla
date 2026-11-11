from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext

from keyboards.reply import get_main_keyboard
from database.queries import upsert_user, get_total_users_count
from config import ADMIN_ID

router = Router()

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, bot: Bot):
    await state.clear()
    user = message.from_user
    
    if user:
        is_premium = bool(getattr(user, "is_premium", False))
        is_new = await upsert_user(
            user_id=user.id,
            username=user.username,
            full_name=user.full_name,
            language_code=user.language_code,
            is_premium=is_premium
        )

        # Notify Admin when a new user enters the bot
        if is_new and ADMIN_ID and user.id != ADMIN_ID:
            try:
                total_users = await get_total_users_count()
                username_str = f"@{user.username}" if user.username else f"<a href='tg://user?id={user.id}'>Profil havolasi</a>"
                premium_str = "Ha ✅ (Premium)" if is_premium else "Yo'q (Oddiy)"
                lang_str = user.language_code or "Noma'lum"

                notify_text = (
                    f"🔔 <b>YANGI FOYDALANUVCHI QO'SHILDI!</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"👤 <b>Foydalanuvchi:</b> {user.full_name}\n"
                    f"🆔 <b>Telegram ID:</b> <code>{user.id}</code>\n"
                    f"🔗 <b>Username:</b> {username_str}\n"
                    f"🌐 <b>Telegram tili:</b> {lang_str}\n"
                    f"⭐ <b>Telegram Premium:</b> {premium_str}\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"📊 <b>Botdagi jami a'zolar:</b> <b>{total_users} nafar</b>"
                )
                await bot.send_message(chat_id=ADMIN_ID, text=notify_text, parse_mode="HTML")
            except Exception:
                pass

    name = user.first_name if user else "Qadrdon"
    text = (
        f"👋 <b>Xush kelibsiz, {name}!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"✨ <b>SOZLA AI</b> — Ingliz tili lug'atini sun'iy intellekt yordamida eng tez va sifatli yodlash platformasi.\n\n"
        f"🎯 <b>Nimalar qila olasiz?</b>\n"
        f"• 📸 <b>Rasm yuborish</b> — Darslikdagi unit sahifasini oling, AI o'zi tarjima qiladi!\n"
        f"• ✍️ <b>Matn yozish</b> — Yangi so'zlarni xabarda yozib yuboring.\n"
        f"• ⚡ <b>Smart Test (Quiz)</b> — 4 variantli testlar bilan mustahkamlash.\n"
        f"• ✍️ <b>Imlo mashqi</b> — So'zlarni klaviaturadan to'g'ri yozish (Spelling).\n"
        f"• 🔴 <b>Spaced Repetition</b> — Xato qilingan qiyin so'zlarni maxsus takrorlash.\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>Quyidagi menyudan kerakli bo'limni tanlang:</i>"
    )
    await message.answer(text, reply_markup=get_main_keyboard(), parse_mode="HTML")

@router.message(F.text == "💡 Qo'llanma va Yordam")
@router.message(Command("help"))
async def cmd_help(message: Message):
    text = (
        "💡 <b>SOZLA AI — Foydalanish bo'yicha qo'llanma:</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "1️⃣ <b>Yangi so'zlar qo'shish:</b>\n"
        "• <i>'📸 Rasm / ✍️ Matndan so'z qo'shish'</i> tugmasini bosing yoki to'g'ridan-to'g'ri kitobdagi lug'at sahifasi rasmini yuboring.\n"
        "• AI so'zlarni, ularning transkripsiyasi va o'zbekcha tarjimalarini aniqlaydi.\n\n"
        "2️⃣ <b>To'plamlar (Unitlar):</b>\n"
        "• So'zlaringizni <i>'Unit 1'</i>, <i>'Destination B2'</i> yoki <i>'IELTS'</i> kabi alohida to'plamlarda saqlang.\n\n"
        "3️⃣ <b>Bilgan va Bilmagan so'zlar filtri:</b>\n"
        "• 🔴 <b>Bilmaganlarim</b>: Testda xato qilingan so'zlar.\n"
        "• 🟡 <b>O'rganilayotganlar</b>: Yangi so'zlar.\n"
        "• 🟢 <b>Yodlanganlar</b>: Ketma-ket 3+ marta to'g'ri topilgan so'zlar.\n\n"
        "4️⃣ <b>Mashq turlari:</b>\n"
        "• ⚡ <b>Test rejimi</b>: 4 ta variantdan tanlash.\n"
        "• ✍️ <b>Imlo mashqi</b>: O'zbekchasiga qarab inglizcha so'zni yozish.\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )
    await message.answer(text, reply_markup=get_main_keyboard(), parse_mode="HTML")

@router.message(F.text == "🔙 Bekor qilish")
async def cancel_action(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Amal bekor qilindi.", reply_markup=get_main_keyboard())

@router.callback_query(F.data == "back_to_menu")
async def cb_back_to_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Asosiy menyuga qaytdingiz.")
    await callback.message.answer("Quyidagi menyudan birini tanlang:", reply_markup=get_main_keyboard())
    await callback.answer()
