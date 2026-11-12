import html
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart, Command, CommandObject
from aiogram.fsm.context import FSMContext

from keyboards.reply import get_main_keyboard
from database.queries import (
    upsert_user,
    get_total_users_count,
    get_unit_share,
    import_shared_unit,
    get_user_stats,
)
from config import ADMIN_ID

router = Router()

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, bot: Bot, command: CommandObject = None):
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

    # Check Deep Link for Unit Sharing: /start share_<code>
    if command and command.args and command.args.startswith("share_"):
        share_code = command.args[6:].strip()
        share = await get_unit_share(share_code)
        if share:
            words = share.get("words", [])
            sample_lines = []
            for i, w in enumerate(words[:5], 1):
                pron = f" <i>[{html.escape(w.get('uz_pronunciation', ''))}]</i>" if w.get("uz_pronunciation") else ""
                sample_lines.append(f"{i}. <b>{html.escape(w['word'])}</b>{pron} — {html.escape(w['translation'])}")

            preview_text = (
                f"🔗 <b>DO'STINGIZ ULASHGAN LUG'AT TO'PLAMI</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"📁 <b>To'plam:</b> {html.escape(share['unit_name'])}\n"
                f"👤 <b>Muallif:</b> {html.escape(share.get('author_name') or 'Foydalanuvchi')}\n"
                f"📚 <b>Jami so'zlar:</b> <b>{len(words)} ta</b>\n\n"
                f"<b>Namuna so'zlar:</b>\n" + "\n".join(sample_lines) + "\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"<i>Ushbu to'plamni o'z hisobingizga saqlab, darhol yodlashni boshlaysizmi?</i>"
            )
            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="📥 O'zimga saqlash (Unitga olish)", callback_data=f"act_import_share:{share_code}")],
                    [InlineKeyboardButton(text="🔙 Asosiy menyu", callback_data="back_to_menu")]
                ]
            )
            await message.answer(preview_text, reply_markup=kb, parse_mode="HTML")
            return

    name = user.first_name if user else "Qadrdon"
    stats = await get_user_stats(user.id) if user else {}
    streak = stats.get("streak", 0)
    streak_badge = f"\n🔥 <b>Kunlik Streak:</b> <b>{streak} kun uzluksiz!</b>\n" if streak > 0 else ""

    text = (
        f"👋 <b>Xush kelibsiz, {name}!</b>{streak_badge}"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"✨ <b>SOZLA AI</b> — Ingliz tili lug'atini sun'iy intellekt yordamida eng tez va sifatli yodlash platformasi.\n\n"
        f"🎯 <b>Nimalar qila olasiz?</b>\n"
        f"• 📸 <b>Rasmdan qo'shish</b> — Darslikdagi unit sahifasini rasmga oling, AI o'zi tarjima va 🗣 o'qilishini chiqaradi!\n"
        f"• ✍️ <b>Yozib qo'shish</b> — Yangi so'zlarni yozib yuboring.\n"
        f"• 📦 <b>Boshlang'ich to'plamlar</b> — Noldan o'rganuvchilar uchun 1 bosishda tayyor Unitlar!\n"
        f"• 🃏 <b>Flashcard (Karta)</b> — So'zlarni audiosi (🔊 / 🐢 Sekin) bilan bitta-bitta yodlash.\n"
        f"• ⚡ <b>Test & 🎧 Listening</b> — Eshitib topish va 4 variantli testlar.\n"
        f"• 🧩 <b>Gap to'ldirish</b> — Kontekstda so'zni topish mashqi.\n"
        f"• ⏰ <b>Avto-Eslatma (Har 15 min)</b> — Xato qilingan so'zlardan avtomatik test (🌙 tungi uyqu rejimi bilan).\n"
        f"• 🔗 <b>Ulashish</b> — O'z Unitlaringizni do'stlarga havola orqali tarqating!\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>Quyidagi menyudan kerakli bo'limni tanlang:</i>"
    )
    await message.answer(text, reply_markup=get_main_keyboard(), parse_mode="HTML")

@router.callback_query(F.data.startswith("act_import_share:"))
async def cb_act_import_share(callback: CallbackQuery):
    share_code = callback.data.split(":")[1]
    res = await import_shared_unit(share_code, callback.from_user.id)
    if not res:
        await callback.answer("To'plam topilmadi yoki eskirgan.", show_alert=True)
        return

    text = (
        f"🎉 <b>MUVAFFAQIYATLI SAQLANDI!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📁 <b>To'plam:</b> {html.escape(res['unit_name'])}\n"
        f"✅ <b>{res['word_count']} ta so'z</b> sizning shaxsiy lug'at bazangizga qo'shildi!\n\n"
        f"Quyidagi mashqlardan birini tanlang:"
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🃏 Flashcard (Karta)", callback_data=f"unit_flashcards:{res['unit_id']}"),
                InlineKeyboardButton(text="⚡ Test (Quiz)", callback_data=f"unit_quiz:{res['unit_id']}")
            ],
            [
                InlineKeyboardButton(text="🎧 Eshitib topish", callback_data=f"unit_listening:{res['unit_id']}"),
                InlineKeyboardButton(text="📄 Word (.docx)", callback_data=f"unit_export_word:{res['unit_id']}")
            ],
            [InlineKeyboardButton(text="🔙 Asosiy menyu", callback_data="back_to_menu")]
        ]
    )
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer("✅ To'plam saqlandi!")

@router.message(F.text == "💡 Qo'llanma va Yordam")
@router.message(Command("help"))
async def cmd_help(message: Message):
    text = (
        "💡 <b>SOZLA AI — Foydalanish bo'yicha qo'llanma:</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "1️⃣ <b>Yangi so'zlar qo'shish:</b>\n"
        "• <i>'📸 Rasmdan so'z qo'shish'</i> — kitob yoki daftar sahifasini rasmga olib tashlang.\n"
        "• <i>'✍️ Yozib so'z qo'shish'</i> — yangi so'zlarni yozib yuboring.\n"
        "• AI so'zlarni, ularning transkripsiyasi va o'zbekcha tarjimalarini aniqlaydi.\n\n"
        "2️⃣ <b>To'plamlar (Unitlar):</b>\n"
        "• So'zlaringizni <i>'Unit 1'</i>, <i>'Destination B2'</i> yoki <i>'IELTS'</i> kabi alohida to'plamlarda saqlang.\n\n"
        "3️⃣ <b>Bilgan va Bilmagan so'zlar filtri:</b>\n"
        "• 🔴 <b>Bilmaganlarim</b>: Testda xato qilingan so'zlar.\n"
        "• 🟡 <b>O'rganilayotganlar</b>: Yangi so'zlar.\n"
        "• 🟢 <b>Yodlanganlar</b>: Ketma-ket 3+ marta to'g'ri topilgan so'zlar.\n\n"
        "4️⃣ <b>Mashq turlari:</b>\n"
        "• 🃏 <b>Flashcard</b>: 🔊 oddiy va 🐢 sekin audio + 🗣 o'zbekcha o'qilishi bilan kartochkada yodlash.\n"
        "• 🎧 <b>Eshitib topish</b>: Inglizcha audio eshitib o'zbekcha tarjimasini topish.\n"
        "• ⚡ <b>Test rejimi</b>: 4 ta variantdan tanlash.\n"
        "• ✍️ <b>Imlo mashqi</b>: O'zbekchasiga qarab inglizcha so'zni yozish.\n"
        "• ⏰ <b>Avto-Eslatma</b>: Har 15 daqiqada xato qilgan so'zlardan tezkor savol (🌙 22:30–07:30 uyqu rejimi bilan).\n"
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
