import asyncio
import os
from database.db import init_db
from database.queries import (
    upsert_user,
    create_unit,
    add_words_bulk,
    get_user_units,
    get_words_by_unit,
    record_answer,
    get_user_stats,
    get_random_distractors,
    get_practice_words
)
from handlers.typing import create_mask, levenshtein_distance

async def run_tests():
    print("🧪 1. Ma'lumotlar bazasini initsializatsiya qilish...")
    await init_db()
    print("   ✅ Baza jadvallari muvaffaqiyatli yaratildi.")

    test_user_id = 99999999
    print("\n🧪 2. Test foydalanuvchisini qo'shish...")
    await upsert_user(test_user_id, "test_user", "Mansur Test")
    print("   ✅ Foydalanuvchi saqlandi.")

    print("\n🧪 3. Yangi Unit yaratish va so'zlar qo'shish...")
    unit_id = await create_unit(test_user_id, "Unit 1 - Test Lug'at")
    test_words = [
        {
            "word": "abandon",
            "transcription": "/əˈbæn.dən/",
            "part_of_speech": "verb",
            "translation": "tashlab ketmoq, tark etmoq",
            "example_en": "They had to abandon their car.",
            "example_uz": "Ular mashinalarini tashlab ketishga majbur bo'lishdi."
        },
        {
            "word": "compulsory",
            "transcription": "/kəmˈpʌl.sər.i/",
            "part_of_speech": "adjective",
            "translation": "majburiy, shart",
            "example_en": "English is a compulsory subject.",
            "example_uz": "Ingliz tili majburiy fandir."
        },
        {
            "word": "reluctant",
            "transcription": "/rɪˈlʌk.tənt/",
            "part_of_speech": "adjective",
            "translation": "istaksiz, xohlamay",
            "example_en": "He was reluctant to leave.",
            "example_uz": "U ketishni istamasdi."
        }
    ]
    added = await add_words_bulk(unit_id, test_user_id, test_words)
    print(f"   ✅ {added} ta so'z Unitga qo'shildi.")

    print("\n🧪 4. 'Bilgan / Bilmagan' mantiqini tekshirish (Spaced Repetition)...")
    words = await get_words_by_unit(unit_id, test_user_id)
    first_word = words[0]
    
    # 1. Testda xato qilinganda -> 'unknown' (🔴) bo'lishi kerak
    status_wrong = await record_answer(test_user_id, first_word["id"], is_correct=False)
    assert status_wrong == "unknown", f"Xato: status 'unknown' bo'lishi kerak edi, lekin {status_wrong} bo'ldi"
    print(f"   ✅ Xato javob berilganda so'z holati: 🔴 '{status_wrong}' ga o'tdi.")

    # 2. Ketma-ket 3 marta to'g'ri topilganda -> 'mastered' (🟢) bo'lishi kerak
    await record_answer(test_user_id, first_word["id"], is_correct=True)
    await record_answer(test_user_id, first_word["id"], is_correct=True)
    status_correct_3 = await record_answer(test_user_id, first_word["id"], is_correct=True)
    assert status_correct_3 == "mastered", f"Xato: status 'mastered' bo'lishi kerak edi, lekin {status_correct_3} bo'ldi"
    print(f"   ✅ 3 marta to'g'ri topilganda so'z holati: 🟢 '{status_correct_3}' ga o'tdi.")

    print("\n🧪 5. Imlo (Spelling) va xatolik masofasini (Levenshtein) tekshirish...")
    mask = create_mask("abandon", 1)
    print(f"   Maslahat maskasi: 'abandon' -> {mask}")
    dist1 = levenshtein_distance("abondon", "abandon") # 1 ta harf xato
    dist2 = levenshtein_distance("apple", "abandon")
    assert dist1 == 1, "Levenshtein masofasi noto'g'ri hisoblandi"
    print(f"   ✅ 'abondon' vs 'abandon' xato harflar soni: {dist1} ta (Kichik imlo xatosi aniqlandi)")

    print("\n🧪 6. Statistika hisob-kitobini tekshirish...")
    stats = await get_user_stats(test_user_id)
    print(f"   ✅ Jami so'zlar: {stats['total_words']} ta | Yodlangan: {stats['mastered_words']} ta | O'rganilmoqda: {stats['learning_words']} ta | Bilmaganlar: {stats['unknown_words']} ta")

    print("\n🎉 BARCHA TIZIM VA BAZA TESTLARI 100% MUVAFFAQIYATLI O'TDI!")

if __name__ == "__main__":
    asyncio.run(run_tests())

