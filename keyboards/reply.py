from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def get_main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="📸 Rasm / ✍️ Matndan so'z qo'shish")
            ],
            [
                KeyboardButton(text="📚 Lug'at to'plamlarim"),
                KeyboardButton(text="📊 Mening natijalarim")
            ],
            [
                KeyboardButton(text="⚡ Test rejimi (Quiz)"),
                KeyboardButton(text="✍️ Imlo mashqi (Spelling)")
            ],
            [
                KeyboardButton(text="⏰ Avto-Eslatma (Har 15 min)"),
                KeyboardButton(text="💡 Qo'llanma va Yordam")
            ]
        ],
        resize_keyboard=True,
        input_field_placeholder="Quyidagi menyulardan birini tanlang..."
    )

def get_cancel_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔙 Bekor qilish")]
        ],
        resize_keyboard=True
    )
