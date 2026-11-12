import html
import re
import urllib.parse
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
from aiogram.fsm.context import FSMContext

from database.queries import (
    get_user_units,
    get_unit,
    delete_unit,
    get_words_by_unit,
    create_or_get_unit_share,
    delete_word,
    get_word_by_id,
)
from keyboards.inline import get_unit_details_keyboard, get_units_keyboard
from keyboards.reply import get_main_keyboard
from services.export_service import generate_unit_word_doc
from services.gemini_service import generate_unit_story
from services.tts_service import generate_speech_bytes

router = Router()

STORY_CACHE = {}

@router.message(F.text == "📚 Lug'at to'plamlarim")
@router.message(F.text == "📚 Mening Unitlarim")
async def show_user_units(message: Message):
    user_id = message.from_user.id
    units = await get_user_units(user_id)
    
    if not units:
        empty_kb = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="📦 Tayyor boshlang'ich to'plamlar", callback_data="open_starter_packs")]]
        )
        await message.answer(
            "📭 <b>Sizda hali hech qanday Unit mavjud emas.</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "• Tayyor so'zlardan boshlash uchun <b>📦 Tayyor boshlang'ich to'plamlar</b> tugmasini bosing;\n"
            "• Yoki <b>📸 Rasmdan so'z qo'shish</b> / <b>✍️ Yozib so'z qo'shish</b> orqali o'z lug'atingizni kiriting!",
            reply_markup=empty_kb,
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
            "➕ Yangi Unit ochish uchun avval <b>📸 Rasmdan so'z qo'shish</b> yoki <b>✍️ Yozib so'z qo'shish</b> tugmasini bosib so'zlarni yuboring.",
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
        uz_pron = f" 🗣 <i>[{w['uz_pronunciation']}]</i>" if w.get("uz_pronunciation") else ""
        trans = f" <code>{w['transcription']}</code>" if w.get("transcription") else ""
        lines.append(f"{emoji} <b>{i}. {w['word'].upper()}</b>{uz_pron}{trans}\n   🇺🇿 {w['translation']}")

    full_text = f"📖 <b>Unit so'zlari ({len(words)} ta):</b>\n━━━━━━━━━━━━━━━━━━━━\n" + "\n\n".join(lines)
    if len(full_text) > 4000:
        full_text = full_text[:3900] + "\n\n<i>... (To'liq ro'yxatni Word fayl sifatida yuklab olishingiz mumkin!)</i>"

    back_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📄 Word (.docx) yuklash", callback_data=f"unit_export_word:{unit_id}"),
                InlineKeyboardButton(text="🗑 So'z o'chirish", callback_data=f"unit_del_menu:{unit_id}")
            ],
            [InlineKeyboardButton(text="🔙 Unitga qaytish", callback_data=f"view_unit:{unit_id}")]
        ]
    )
    await callback.message.edit_text(full_text, reply_markup=back_kb, parse_mode="HTML")
    await callback.answer()

# --- Unit Sharing ---
@router.callback_query(F.data.startswith("unit_share:"))
async def cb_share_unit(callback: CallbackQuery, bot: Bot):
    unit_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id

    unit = await get_unit(unit_id, user_id)
    if not unit:
        await callback.answer("Unit topilmadi!", show_alert=True)
        return

    words = await get_words_by_unit(unit_id, user_id)
    if not words:
        await callback.answer("Bu Unitda hali so'zlar yo'q!", show_alert=True)
        return

    share = await create_or_get_unit_share(unit_id, user_id)
    if not share:
        await callback.answer("Ulashish havolasini yaratishda xatolik.", show_alert=True)
        return

    bot_info = await bot.get_me()
    share_link = f"https://t.me/{bot_info.username}?start=share_{share['share_code']}"
    share_text = f"📚 Men '{unit['name']}' to'plamini Sozla AI botida yodlayapman! Barcha {len(words)} ta so'zni o'rganish uchun havolani bosing 👇"
    tg_share_url = f"https://t.me/share/url?url={urllib.parse.quote(share_link)}&text={urllib.parse.quote(share_text)}"

    downloads = share.get("downloads_count", 0)
    text = (
        f"🔗 <b>'{html.escape(unit['name'])}' TO'PLAMINI ULASHISH</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Ushbu havola orqali do'stingiz yoki o'quvchilaringiz kirsa, "
        f"barcha <b>{len(words)} ta so'z</b> (talaffuz, tarjima va misollari bilan) "
        f"ularning hisobiga <b>1 bosishda</b> nusxalanadi!\n\n"
        f"📥 <i>Yuklab olingan: {downloads} marta</i>\n\n"
        f"🔗 <b>Sizning shaxsiy havolangiz:</b>\n"
        f"<code>{share_link}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚀 Telegram orqali yuborish", url=tg_share_url)],
            [InlineKeyboardButton(text="🔙 Unitga qaytish", callback_data=f"view_unit:{unit_id}")]
        ]
    )
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()

# --- AI Story Generator ---
@router.callback_query(F.data.startswith("unit_story:"))
async def cb_unit_story(callback: CallbackQuery):
    unit_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id

    unit = await get_unit(unit_id, user_id)
    if not unit:
        await callback.answer("Unit topilmadi!", show_alert=True)
        return

    words = await get_words_by_unit(unit_id, user_id)
    if not words:
        await callback.answer("Hikoya tuzish uchun Unitda so'zlar bo'lishi kerak!", show_alert=True)
        return

    await callback.answer("🧠 AI hikoya yozmoqda, iltimos kuting...")
    wait_msg = await callback.message.answer(
        "🧠 <b>Sozla AI hikoya to'qimoqda...</b> ⏳\n"
        f"<i>'{unit['name']}' to'plamidagi so'zlarni qiziqarli kontekstga bog'lamoqda...</i>",
        parse_mode="HTML"
    )

    try:
        story = await generate_unit_story(unit["name"], words)
        cache_id = f"{unit_id}_{user_id}"
        STORY_CACHE[cache_id] = story

        used_str = ", ".join(f"<b>{html.escape(w)}</b>" for w in story.get("used_words", []))
        text = (
            f"📖 <b>{html.escape(story.get('title_en', 'Story'))}</b>\n"
            f"<i>({html.escape(story.get('title_uz', 'Hikoya'))})</i>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{story['story_en']}\n\n"
            f"🇺🇿 <b>O'zbekcha tarjimasi:</b>\n"
            f"<i>{html.escape(story.get('story_uz', ''))}</i>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🎯 <b>Qatnashgan so'zlar:</b> {used_str}"
        )

        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="🔊 Hikoyani tinglash (TTS)", callback_data=f"story_tts:{cache_id}"),
                    InlineKeyboardButton(text="🔄 Boshqa hikoya", callback_data=f"unit_story:{unit_id}")
                ],
                [InlineKeyboardButton(text="🔙 Unitga qaytish", callback_data=f"view_unit:{unit_id}")]
            ]
        )
        await wait_msg.delete()
        await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")
    except Exception as e:
        await wait_msg.edit_text(f"❌ Hikoya tuzishda xatolik yuz berdi: {str(e)[:100]}")

@router.callback_query(F.data.startswith("story_tts:"))
async def cb_story_tts(callback: CallbackQuery):
    cache_id = callback.data.split(":")[1]
    story = STORY_CACHE.get(cache_id)
    if not story:
        await callback.answer("Hikoya topilmadi.", show_alert=True)
        return

    # Clean story text for speech (strip HTML tags)
    clean_text = re.sub(r"<[^>]+>", "", story.get("story_en", "")).strip()
    if not clean_text:
        await callback.answer("Audio uchun matn topilmadi.", show_alert=True)
        return

    await callback.answer("🔊 Audio tayyorlanmoqda...")
    try:
        # Generate speech for story
        audio_fp = await generate_speech_bytes(clean_text[:500], slow=False)
        voice_file = BufferedInputFile(audio_fp.read(), filename="story.mp3")
        await callback.message.answer_voice(
            voice=voice_file,
            caption=f"🔊 <b>{html.escape(story.get('title_en', 'Hikoya'))}</b>",
            parse_mode="HTML"
        )
    except Exception:
        await callback.answer("Audio generatsiyasida xatolik.", show_alert=True)

# --- Delete Single Word Menu ---
@router.callback_query(F.data.startswith("unit_del_menu:"))
async def cb_unit_del_menu(callback: CallbackQuery):
    unit_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id

    words = await get_words_by_unit(unit_id, user_id)
    if not words:
        await callback.answer("So'zlar yo'q.", show_alert=True)
        return

    buttons = []
    for w in words[:25]:
        buttons.append([
            InlineKeyboardButton(
                text=f"🗑 {w['word']} — {w['translation'][:20]}",
                callback_data=f"del_word_act:{unit_id}:{w['id']}"
            )
        ])
    buttons.append([InlineKeyboardButton(text="🔙 Unit so'zlariga qaytish", callback_data=f"unit_words:{unit_id}")])

    await callback.message.edit_text(
        "🗑 <b>O'chirmoqchi bo'lgan so'zni tanlang:</b>\n━━━━━━━━━━━━━━━━━━━━",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("del_word_act:"))
async def cb_del_word_act(callback: CallbackQuery):
    parts = callback.data.split(":")
    unit_id = int(parts[1])
    word_id = int(parts[2])
    user_id = callback.from_user.id

    word = await get_word_by_id(word_id, user_id)
    word_name = word["word"] if word else "So'z"

    await delete_word(word_id, user_id)
    await callback.answer(f"✅ '{word_name}' muvaffaqiyatli o'chirildi!", show_alert=True)
    await cb_show_unit_words(callback)

@router.callback_query(F.data.startswith("unit_export_word:"))
async def cb_export_unit_word(callback: CallbackQuery):
    unit_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id

    unit = await get_unit(unit_id, user_id)
    if not unit:
        await callback.answer("Unit topilmadi!", show_alert=True)
        return

    words = await get_words_by_unit(unit_id, user_id)
    if not words:
        await callback.answer("Bu Unitda so'zlar yo'q!", show_alert=True)
        return

    await callback.answer("📄 Word hujjati tayyorlanmoqda...")
    
    docx_buffer = await generate_unit_word_doc(unit["name"], words)
    safe_name = re.sub(r'[^\w\s-]', '', unit["name"]).strip().replace(' ', '_') or f"Unit_{unit_id}"
    filename = f"{safe_name}_SozlaAI.docx"

    doc_file = BufferedInputFile(docx_buffer.read(), filename=filename)
    await callback.message.answer_document(
        document=doc_file,
        caption=(
            f"📄 <b>{unit['name']} — Word Lug'at Fayli</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📚 Jami: <b>{len(words)} ta so'z</b>\n"
            f"<i>Chop etish va o'qish uchun tayyor chiroyli jadval ko'rinishida!</i>"
        ),
        parse_mode="HTML"
    )

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
