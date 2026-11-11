# 📚 Smart Vocabulary Bot (AI Lug'at Yodlash Boti)
### Mukammal Arxitektura va Amalga Oshirish Rejasi (Project Plan)

---

## 1. 🎯 Loyiha Maqsadi va Asosiy Imkoniyatlari

Foydalanuvchilarga ingliz tili so'zlarini eng qulay usulda yig'ish, ularni guruhlarga ajratish hamda **"Bilganlarim" va "Bilmaganlarim"** tamoyili (Spaced Repetition) asosida oson va tez yodlatish.

---

## 2. 📥 So'z Qo'shish Imkoniyatlari (Multi-Input)

Foydalanuvchi so'zlarni 2 xil usulda qo'shishi mumkin:

```
                  ┌───────────────────────────────┐
                  │    Foydalanuvchi Kiritishi    │
                  └──────────────┬────────────────┘
                                 │
                 ┌───────────────┴───────────────┐
                 ▼                               ▼
       📷 RASM YUBORISH                  ✍️ MATN YOZISH
   (Kitob sahifasi, daftar,        (Bitta so'z, vergul bilan ro'yxat,
   lug'at ro'yxati skrinshoti)      yoki erkin matn/maqola)
                 │                               │
                 └───────────────┬───────────────┘
                                 ▼
                     🧠 Google Gemini AI Tahlili
                     - So'zlarni ajratish
                     - Transkripsiyani topish
                     - Aniq o'zbekcha tarjimasi
                     - So'z turkumi va namuna gap
                                 │
                                 ▼
                     💾 Baza (DB) ga saqlash
```

1. **📷 Rasm orqali (Vision OCR)**:
   - Darslik (masalan, *Destination B1, English File, IELTS Wordlist*) sahifasini rasmga olib tashlaydi.
   - AI matnni o'qib, so'zlarni toza ajratib oladi.
2. **✍️ Matn orqali (Text Input)**:
   - Foydalanuvchi shunchaki yozib yuboradi:
     - *Masalan 1:* `abandon, compulsory, reluctant, deliberate`
     - *Masalan 2:* Bir dona so'z: `sophisticated`
     - *Masalan 3:* So'z va uning tarjimasi: `apple - olma, peach - shaftoli`
   - AI kiritilgan matndan so'zlarni chiqarib, yetishmayotgan tarjima, transkripsiya va misollarni o'zi to'ldiradi.

---

## 3. 🗂️ So'zlarni Guruhlash Tizimi (Grouping Architecture)

So'zlar 2 xil o'lchamda tartiblanadi:

### A. To'plamlar / Unitlar bo'yicha (Strukturaviy)
- Foydalanuvchi har bir kiritgan lug'atiga nom beradi:
  - 📁 *Unit 1 - Family & Friends*
  - 📁 *Destination B2 - Unit 4*
  - 📁 *IELTS 7.0 Academic Words*
  - 📁 *Umumiy / Boshqa so'zlar*

### B. O'zlashtirish Darajasi bo'yicha (Dinamik Filtrlar)
Har bir so'z o'rganilish holatiga qarab avtomatik 3 guruhga ajraladi:

| Guruh | Belgisi | Tavsifi |
| :--- | :---: | :--- |
| **🔴 Bilmaganlarim (Qiyin so'zlar)** | `❌` | Test yoki yozishda xato qilingan, hali yaxshi esda qolmagan so'zlar. |
| **🟡 O'rganilayotganlar** | `⏳` | 1-2 marta to'g'ri topilgan, lekin to'liq mustahkamlanmagan so'zlar. |
| **🟢 Bilganlarim (Yodlanganlar)** | `✅` | Ketma-ket 3+ marta to'g'ri yozilgan yoki topilgan so'zlar. |

> **Aqlli algoritm (Spaced Repetition)**: Mashq paytida bot asosan **🔴 Bilmagan so'zlar**ni ko'proq takrorlatadi.

---

## 4. 🎮 Mashq va Yodlash Rejimlari (Learning Modes)

Foydalanuvchi qaysi Unitni va qaysi toifani mashq qilishni tanlaydi (masalan: *"Faqat Unit 3 dagi bilmagan so'zlarimdan test ol"*):

1. **🅰️ Variantli Test (Quiz Mode)**:
   - 4 ta variantdan to'g'ri javobni tanlash.
   - 2 yo'nalishda: `EN ➡️ UZ` va `UZ ➡️ EN`.
   - Noto'g'ri tanlansa, so'z avtomatik **🔴 Bilmaganlarim** ro'yxatiga qo'shiladi.

2. **✍️ Yozma Mashq (Spelling / Typing Mode)**:
   - Bot so'zning o'zbekcha tarjimasi va birinchi harfini ko'rsatadi:
     > *"tashlab ketmoq, tark etmoq"* (a_______)
   - Foydalanuvchi to'g'ri imloda `abandon` deb yozishi shart.
   - Harflarda xatolik bo'lsa, AI/algoritm qayerida xato ketganini ko'rsatib to'g'rilashni o'rgatadi.

3. **🃏 Flashcard (Kartalar Rejimi)**:
   - So'z va transkripsiya chiqadi.
   - "Tarjimani ko'rish" tugmasi bosiladi.
   - Foydalanuvchi o'zi baholaydi: `[Bilaman ✅]` yoki `[Bilmayman ❌]`.

4. **🔊 Audio talaffuz (TTS)**:
   - Har bir so'zning to'g'ri inglizcha audiosi (`gTTS` orqali) birga jo'natiladi.

---

## 5. 🗄️ Ma'lumotlar Bazasi Sxemasi (Database Schema)

```sql
-- 1. Foydalanuvchilar
CREATE TABLE users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    full_name TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Lug'at to'plamlari (Unitlar)
CREATE TABLE units (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(user_id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. So'zlar
CREATE TABLE words (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    unit_id INTEGER REFERENCES units(id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES users(user_id) ON DELETE CASCADE,
    word TEXT NOT NULL,
    transcription TEXT,
    part_of_speech TEXT,
    translation TEXT NOT NULL,
    example_en TEXT,
    example_uz TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 4. Bilgan/Bilmagan holati (Progress & Spaced Repetition)
CREATE TABLE user_word_progress (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(user_id) ON DELETE CASCADE,
    word_id INTEGER REFERENCES words(id) ON DELETE CASCADE,
    correct_count INTEGER DEFAULT 0,
    incorrect_count INTEGER DEFAULT 0,
    status TEXT DEFAULT 'learning', -- 'unknown', 'learning', 'mastered'
    last_reviewed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, word_id)
);
```

---

## 6. 📁 Loyiha Strukturasi (Project Architecture)

```
Lugat/
├── .env                  # BOT_TOKEN, GEMINI_API_KEY
├── .env.example
├── requirements.txt      # Kutubxonalar ro'yxati
├── main.py               # Botni ishga tushiruvchi asosiy fayl
├── config.py             # Sozlamalar va muhit o'zgaruvchilari
├── database/
│   ├── __init__.py
│   ├── db.py             # SQLite ulanishi va jadvallarni yaratish
│   └── queries.py        # So'zlar, unitlar va progress bo'yicha SQL so'rovlar
├── services/
│   ├── __init__.py
│   ├── gemini_service.py # OCR va Matndan lug'at ajratib olish (Gemini AI)
│   └── tts_service.py    # So'zlarni ovozli qilib berish (Audio talaffuz)
├── handlers/
│   ├── __init__.py
│   ├── common.py         # /start, /help, asosiy menyu
│   ├── add_words.py      # Rasm yoki matn qabul qilish, tahlil qilish
│   ├── units.py          # Unitlarni ko'rish, boshqarish, o'chirish
│   ├── quiz.py           # Variantli test o'tkazish
│   ├── typing.py         # Yozish mashqi (Spelling)
│   └── stats.py          # Bilganlarim / Bilmaganlarim statistikasi
├── keyboards/
│   ├── reply.py          # Asosiy doimiy menyular
│   └── inline.py         # Test variantlari, tasdiqlash va Unit tugmalari
└── states/
    └── bot_states.py     # Aiogram FSM (rasm kutish, matn kutish, yozish mashqi)
```

---

## 7. 🚀 Bosqichma-bosqich Bajarish Rejasi (Milestones)

- [x] **1-qadam**: Virtual muhit (`venv`) va loyiha arxitekturasini o'rnatish.
- [ ] **2-qadam**: Ma'lumotlar bazasi (`database/db.py`, `database/queries.py`) modullarini tuzish.
- [ ] **3-qadam**: Gemini AI servisi (`services/gemini_service.py`) — rasm va matnni toza JSON lug'atga aylantirish.
- [ ] **4-qadam**: So'z qo'shish handleri (`handlers/add_words.py`) — rasm yoki matn kelganda avtomatik tahlil qilib, tasdiqlash bilan Unitga saqlash.
- [ ] **5-qadam**: Unitlar va Bilgan/Bilmaganlar filtrlari (`handlers/units.py`, `handlers/stats.py`).
- [ ] **6-qadam**: Variantli test (Quiz) rejimi (`handlers/quiz.py`).
- [ ] **7-qadam**: Yozma mashq (Spelling) rejimi (`handlers/typing.py`).
- [ ] **8-qadam**: TTS Audio talaffuz integratsiyasi va yakuniy sinov.

