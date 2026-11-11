# 📚 Smart Vocabulary Bot (AI Lug'at Yodlash Boti)

Ushbu bot ingliz tili so'zlarini tez va samarali yodlash uchun maxsus yaratilgan Telegram botdir.

---

## 🌟 Asosiy Imkoniyatlar

1. **📸 Rasm orqali so'z qo'shish (Vision OCR)**:
   - Darslik (masalan: *Destination B1, English File, IELTS Wordlist*) sahifasini rasmga olib yuborasiz.
   - Google Gemini 2.5 AI rasmdagi so'zlarni, transkripsiyalarini, aniq o'zbekcha tarjimalarini va namuna gaplarini avtomatik ajratib beradi.

2. **✍️ Matn orqali so'z qo'shish**:
   - So'zlarni bittalab yoki vergul bilan ro'yxat ko'rinishida yozib yuborsangiz ham (masalan: `abandon, compulsory, reluctant`), AI to'liq lug'at qilib shakllantiradi.

3. **📁 Unitlar va Guruhlash**:
   - So'zlarni o'zingiz istagan Unitlarga (masalan: *Unit 1, Unit 2, IELTS Words*) saqlash va boshqarish.

4. **🔴 Bilganlarim va Bilmaganlarim (Spaced Repetition)**:
   - 🔴 **Bilmaganlarim (Qiyin so'zlar)**: Test yoki yozishda xato qilingan so'zlar.
   - 🟡 **O'rganilayotganlar**: Yangi yoki 1-2 marta to'g'ri topilganlar.
   - 🟢 **Yodlanganlar**: Ketma-ket 3+ marta to'g'ri topilgan so'zlar.

5. **🅰️ Variantli Test (Quiz)**:
   - 4 ta variantdan to'g'ri javobni tanlash. Xato qilinsa, so'z avtomatik 🔴 Bilmaganlar ro'yxatiga tushadi.

6. **✍️ Yozma Mashq (Spelling / Imlo)**:
   - O'zbekcha ma'nosi va harflar shabloniga qarab inglizcha so'zni klaviaturadan to'g'ri yozish.
   - Harflarda adashilsa, AI imlo xatosini ko'rsatib maslahat beradi.
   - To'g'ri topilganda so'zning **audio talaffuzi (TTS)** jo'natiladi.

---

## 🚀 Ishga Tushirish Qo'llanmasi

### 1. `.env` Faylini Sozlash
Loyiha papkasidagi `.env` faylini oching va quyidagi 2 ta kalitni kiriting:

```env
BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ  # Telegram @BotFather dan olingan token
GEMINI_API_KEY=AIzaSy...                         # aistudio.google.com dan olingan bepul API kalit
DATABASE_PATH=data/lugat.db
```

### 2. Botni Ishga Tushirish
Terminalda quyidagi buyruqni bering:

```powershell
.\venv\Scripts\python main.py
```

---

## 📂 Fayllar Tuzilishi
- `main.py` — Botning asosiy boshqaruvchi fayli
- `PROJECT_PLAN.md` — Loyihaning to'liq arxitekturaviy rejasi
- `config.py` — Sozlamalar va muhit o'zgaruvchilari
- `database/` — SQLite bazasi va barcha SQL so'rovlar
- `services/gemini_service.py` — Gemini 2.5 Flash Vision AI servisi
- `services/tts_service.py` — Audio talaffuz yaratuvchi servis
- `handlers/` — Botning barcha buyruq va menyulari (Rasm/Matn qo'shish, Unitlar, Test, Yozma mashq, Statistika)

