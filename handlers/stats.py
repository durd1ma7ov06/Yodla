from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from database.queries import get_user_stats, get_practice_words
from keyboards.reply import get_main_keyboard
from utils.ui_helpers import progress_bar

router = Router()

@router.message(F.text == "📊 Mening natijalarim")
@router.message(F.text == "📊 Statistika (Bilgan / Bilmagan)")
async def show_statistics(message: Message):
    user_id = message.from_user.id
    stats = await get_user_stats(user_id)
    total = stats["total_words"]

    if total == 0:
        await message.answer(
            "📊 <b>Sizda hali hech qanday so'zlar mavjud emas.</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "Lug'at qo'shish uchun <b>📸 Rasm / ✍️ Matndan so'z qo'shish</b> tugmasini bosing!",
            reply_markup=get_main_keyboard(),
            parse_mode="HTML"
        )
        return

    mastered = stats["mastered_words"]
    learning = stats["learning_words"]
    unknown = stats["unknown_words"]

    mastered_percent = round((mastered / total * 100), 1)
    unknown_percent = round((unknown / total * 100), 1)
    learning_percent = round((learning / total * 100), 1)

    bar_mastered = progress_bar(mastered, total, length=8)

    text = (
        "📊 <b>SOZLA AI — BILIM DARANGIZ:</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"📚 Jami lug'at bazangiz: <b>{total} ta so'z</b>\n\n"
        f"🟢 <b>Yodlanganlar:</b> {mastered} ta ({mastered_percent}%)\n"
        f"<code>{bar_mastered}</code>\n"
        f"<i>(3+ marta to'g'ri topilgan so'zlar)</i>\n\n"
        f"🟡 <b>O'rganilayotganlar:</b> {learning} ta ({learning_percent}%)\n"
        f"<i>(Yangi va o'rganish jarayonidagi so'zlar)</i>\n\n"
        f"🔴 <b>Bilmaganlarim / Qiyin so'zlar:</b> {unknown} ta ({unknown_percent}%)\n"
        f"<i>(Mashqlarda xato qilingan so'zlar)</i>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "💡 <i>Tavsiya: Har kuni avvalo 🔴 'Qiyin so'zlar'dan test topshiring!</i>"
    )

    buttons = []
    if unknown > 0:
        buttons.append([InlineKeyboardButton(text="🔴 Qiyin so'zlar ro'yxatini ko'rish", callback_data="view_difficult_words")])
        buttons.append([InlineKeyboardButton(text="⚡ Faqat qiyin so'zlardan test", callback_data="quiz_filter:all:unknown")])
        buttons.append([InlineKeyboardButton(text="🎧 Faqat qiyin so'zlarni eshitib topish", callback_data="listen_filter:all:unknown")])
        buttons.append([InlineKeyboardButton(text="✍️ Faqat qiyin so'zlardan imlo", callback_data="typing_filter:all:unknown")])
    buttons.append([InlineKeyboardButton(text="🔙 Menyuga qaytish", callback_data="back_to_menu")])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer(text, reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data == "view_difficult_words")
async def cb_view_difficult_words(callback: CallbackQuery):
    user_id = callback.from_user.id
    difficult_words = await get_practice_words(user_id, status_filter="unknown", limit=50)

    if not difficult_words:
        await callback.answer("Sizda qiyin so'zlar yo'q! Barakalla! 🎉", show_alert=True)
        return

    lines = []
    for i, w in enumerate(difficult_words, 1):
        trans = f" <code>{w['transcription']}</code>" if w.get('transcription') else ""
        lines.append(f"🔴 <b>{i}. {w['word'].upper()}</b>{trans}\n   🇺🇿 {w['translation']}")

    full_text = f"🔴 <b>Qiyin / Bilmagan so'zlaringiz ({len(difficult_words)} ta):</b>\n━━━━━━━━━━━━━━━━━━━━\n" + "\n\n".join(lines)
    if len(full_text) > 4000:
        full_text = full_text[:3900] + "\n\n<i>... (ko'proq so'zlar bor)</i>"

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⚡ Bularni test bilan yodlash", callback_data="quiz_filter:all:unknown")],
            [InlineKeyboardButton(text="🔙 Statistikaga qaytish", callback_data="back_to_stats")]
        ]
    )
    await callback.message.edit_text(full_text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "back_to_stats")
async def cb_back_to_stats(callback: CallbackQuery):
    user_id = callback.from_user.id
    stats = await get_user_stats(user_id)
    total = stats["total_words"]
    mastered = stats["mastered_words"]
    learning = stats["learning_words"]
    unknown = stats["unknown_words"]

    mastered_percent = round((mastered / total * 100), 1) if total > 0 else 0
    unknown_percent = round((unknown / total * 100), 1) if total > 0 else 0
    learning_percent = round((learning / total * 100), 1) if total > 0 else 0

    text = (
        "📊 <b>SOZLA AI — BILIM DARANGIZ:</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"📚 Jami so'zlar: <b>{total} ta</b>\n\n"
        f"🟢 <b>Yodlanganlar:</b> {mastered} ta ({mastered_percent}%)\n"
        f"🟡 <b>O'rganilayotganlar:</b> {learning} ta ({learning_percent}%)\n"
        f"🔴 <b>Bilmaganlarim:</b> {unknown} ta ({unknown_percent}%)\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )

    buttons = []
    if unknown > 0:
        buttons.append([InlineKeyboardButton(text="🔴 Qiyin so'zlar ro'yxatini ko'rish", callback_data="view_difficult_words")])
        buttons.append([InlineKeyboardButton(text="⚡ Faqat qiyin so'zlardan test", callback_data="quiz_filter:all:unknown")])
    buttons.append([InlineKeyboardButton(text="🔙 Menyuga qaytish", callback_data="back_to_menu")])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()
