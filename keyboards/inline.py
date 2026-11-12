from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from typing import List, Dict, Any, Optional

def get_units_keyboard(units: List[Dict[str, Any]], action_prefix: str) -> InlineKeyboardMarkup:
    """Build keyboard with units."""
    buttons = []
    for u in units:
        btn_text = f"📁 {u['name']} ({u.get('word_count', 0)} ta)"
        buttons.append([InlineKeyboardButton(text=btn_text, callback_data=f"{action_prefix}:{u['id']}")])
        
    buttons.append([InlineKeyboardButton(text="➕ Yangi Unit ochish", callback_data=f"{action_prefix}:new")])
    buttons.append([InlineKeyboardButton(text="🔙 Menyuga qaytish", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_practice_filter_keyboard(prefix: str, unit_id: Optional[int] = None) -> InlineKeyboardMarkup:
    uid_str = str(unit_id) if unit_id is not None else "all"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔴 Faqat bilmaganlarim", callback_data=f"{prefix}:{uid_str}:unknown"),
                InlineKeyboardButton(text="🟡 O'rganilayotganlar", callback_data=f"{prefix}:{uid_str}:learning")
            ],
            [
                InlineKeyboardButton(text="🟢 Yodlanganlar", callback_data=f"{prefix}:{uid_str}:mastered"),
                InlineKeyboardButton(text="🔄 Barcha so'zlar", callback_data=f"{prefix}:{uid_str}:all")
            ],
            [InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_to_menu")]
        ]
    )

def get_unit_details_keyboard(unit_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📖 So'zlar ro'yxati", callback_data=f"unit_words:{unit_id}"),
                InlineKeyboardButton(text="📄 Word (.docx) yuklash", callback_data=f"unit_export_word:{unit_id}")
            ],
            [
                InlineKeyboardButton(text="🃏 Flashcard (Karta)", callback_data=f"unit_flashcards:{unit_id}"),
                InlineKeyboardButton(text="⚡ Test boshlash", callback_data=f"unit_quiz:{unit_id}")
            ],
            [
                InlineKeyboardButton(text="🎧 Eshitib topish", callback_data=f"unit_listening:{unit_id}"),
                InlineKeyboardButton(text="🧩 Gap to'ldirish", callback_data=f"unit_context:{unit_id}")
            ],
            [
                InlineKeyboardButton(text="📖 AI bilan hikoya", callback_data=f"unit_story:{unit_id}"),
                InlineKeyboardButton(text="🔗 Do'stlarga ulashish", callback_data=f"unit_share:{unit_id}")
            ],
            [
                InlineKeyboardButton(text="✍️ Imlo mashqi", callback_data=f"unit_typing:{unit_id}"),
                InlineKeyboardButton(text="🗑 Unitni o'chirish", callback_data=f"unit_delete:{unit_id}")
            ],
            [InlineKeyboardButton(text="🔙 Unitlar ro'yxatiga qaytish", callback_data="back_to_units")]
        ]
    )

def get_confirm_save_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Unitga saqlash", callback_data="confirm_save_words"),
                InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_save_words")
            ]
        ]
    )

def get_quiz_options_keyboard(options: List[str], correct_index: int, session_id: str) -> InlineKeyboardMarkup:
    buttons = []
    for i, opt in enumerate(options):
        display_text = opt[:30] + ("..." if len(opt) > 30 else "")
        buttons.append([InlineKeyboardButton(text=f"{chr(65+i)}) {display_text}", callback_data=f"qz:{session_id}:{i}")])
    buttons.append([InlineKeyboardButton(text="🛑 Testni yakunlash", callback_data=f"qz:{session_id}:stop")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_typing_action_keyboard(word_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔊 Talaffuzini eshitish", callback_data=f"tts_word:{word_id}"),
                InlineKeyboardButton(text="💡 Maslahat (Hint)", callback_data="typing_hint")
            ],
            [
                InlineKeyboardButton(text="⏭ O'tkazib yuborish", callback_data="typing_skip"),
                InlineKeyboardButton(text="🛑 To'xtatish", callback_data="typing_stop")
            ]
        ]
    )
