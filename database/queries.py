import json
from typing import List, Dict, Optional, Any
from .db import get_db_connection

# --- User Queries ---
async def upsert_user(
    user_id: int,
    username: Optional[str],
    full_name: str,
    language_code: Optional[str] = None,
    is_premium: bool = False
) -> bool:
    """
    Saves or updates user. Returns True if this is a brand new user, False if already exists.
    """
    async with get_db_connection() as db:
        cursor = await db.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
        existing = await cursor.fetchone()
        is_new = existing is None

        await db.execute("""
            INSERT INTO users (user_id, username, full_name, language_code, is_premium, last_active_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                full_name = excluded.full_name,
                language_code = excluded.language_code,
                is_premium = excluded.is_premium,
                last_active_at = CURRENT_TIMESTAMP;
        """, (user_id, username, full_name, language_code, 1 if is_premium else 0))
        await db.commit()
        return is_new

async def get_total_users_count() -> int:
    async with get_db_connection() as db:
        cursor = await db.execute("SELECT COUNT(*) as cnt FROM users")
        row = await cursor.fetchone()
        return row["cnt"] if row else 0

async def get_all_users() -> List[Dict[str, Any]]:
    async with get_db_connection() as db:
        cursor = await db.execute("""
            SELECT user_id, username, full_name, language_code, is_premium, created_at, last_active_at
            FROM users
            ORDER BY created_at DESC
        """)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

async def get_global_stats() -> Dict[str, Any]:
    async with get_db_connection() as db:
        u_cur = await db.execute("SELECT COUNT(*) as c FROM users")
        u_cnt = (await u_cur.fetchone())["c"]

        w_cur = await db.execute("SELECT COUNT(*) as c FROM words")
        w_cnt = (await w_cur.fetchone())["c"]

        unit_cur = await db.execute("SELECT COUNT(*) as c FROM units")
        unit_cnt = (await unit_cur.fetchone())["c"]

        keys_cur = await db.execute("SELECT COUNT(*) as c FROM api_keys WHERE is_active = 1")
        keys_cnt = (await keys_cur.fetchone())["c"]

        prog_cur = await db.execute("""
            SELECT 
                SUM(CASE WHEN status = 'mastered' THEN 1 ELSE 0 END) as mastered,
                SUM(CASE WHEN status = 'unknown' THEN 1 ELSE 0 END) as unknown
            FROM user_word_progress
        """)
        prog = await prog_cur.fetchone()
        return {
            "users": u_cnt,
            "units": unit_cnt,
            "words": w_cnt,
            "api_keys": keys_cnt,
            "mastered": prog["mastered"] or 0,
            "unknown": prog["unknown"] or 0
        }

# --- Auto-Send / 15-Min Vocabulary Drip Queries ---
async def get_user_auto_settings(user_id: int) -> Dict[str, Any]:
    async with get_db_connection() as db:
        cursor = await db.execute("""
            SELECT COALESCE(auto_send_enabled, 1) as enabled,
                   COALESCE(auto_send_interval, 15) as interval,
                   COALESCE(quiet_hours_enabled, 1) as quiet_hours_enabled,
                   last_auto_sent_at
            FROM users WHERE user_id = ?
        """, (user_id,))
        row = await cursor.fetchone()
        if not row:
            return {"enabled": 1, "interval": 15, "quiet_hours_enabled": 1, "last_auto_sent_at": None}
        return dict(row)

async def update_user_auto_settings(
    user_id: int,
    enabled: Optional[int] = None,
    interval: Optional[int] = None,
    quiet_hours_enabled: Optional[int] = None,
):
    async with get_db_connection() as db:
        if enabled is not None:
            await db.execute("UPDATE users SET auto_send_enabled = ? WHERE user_id = ?", (enabled, user_id))
        if interval is not None:
            await db.execute("UPDATE users SET auto_send_interval = ? WHERE user_id = ?", (interval, user_id))
        if quiet_hours_enabled is not None:
            await db.execute("UPDATE users SET quiet_hours_enabled = ? WHERE user_id = ?", (quiet_hours_enabled, user_id))
        await db.commit()

async def get_users_due_for_auto_word() -> List[Dict[str, Any]]:
    """Returns users who have auto_send_enabled=1, have at least 1 word, and interval has elapsed."""
    async with get_db_connection() as db:
        cursor = await db.execute("""
            SELECT u.user_id, u.full_name,
                   COALESCE(u.auto_send_interval, 15) as interval,
                   COALESCE(u.quiet_hours_enabled, 1) as quiet_hours_enabled
            FROM users u
            WHERE COALESCE(u.auto_send_enabled, 1) = 1
              AND EXISTS (SELECT 1 FROM words w WHERE w.user_id = u.user_id)
              AND (
                  u.last_auto_sent_at IS NULL
                  OR (strftime('%s', 'now') - strftime('%s', u.last_auto_sent_at)) >= (COALESCE(u.auto_send_interval, 15) * 60)
              )
        """)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

async def get_next_word_for_auto_send(user_id: int) -> Optional[Dict[str, Any]]:
    """
    Picks a random mistaken word first for spaced repetition quiz:
    1. 'unknown' words (currently mistaken / not known)
    2. 'learning' words with past mistakes (incorrect_count > 0)
    3. 'learning' words (new / in progress)
    4. 'mastered' words (review)
    Within the highest priority group, avoids repeating the exact last sent word and picks randomly.
    """
    async with get_db_connection() as db:
        cursor = await db.execute("""
            SELECT w.*, un.name as unit_name,
                   COALESCE(p.status, 'learning') as status,
                   COALESCE(p.incorrect_count, 0) as incorrect_count,
                   p.last_reviewed_at
            FROM words w
            LEFT JOIN units un ON un.id = w.unit_id
            LEFT JOIN user_word_progress p ON p.word_id = w.id AND p.user_id = w.user_id
            WHERE w.user_id = ?
            ORDER BY
                CASE
                    WHEN COALESCE(p.status, 'learning') = 'unknown' THEN 1
                    WHEN COALESCE(p.incorrect_count, 0) > 0 AND COALESCE(p.status, 'learning') != 'mastered' THEN 2
                    WHEN COALESCE(p.status, 'learning') = 'learning' THEN 3
                    ELSE 4
                END ASC,
                CASE
                    WHEN w.id = COALESCE((SELECT word_id FROM auto_challenges WHERE user_id = ? ORDER BY id DESC LIMIT 1), -1) THEN 1
                    ELSE 0
                END ASC,
                RANDOM()
            LIMIT 1
        """, (user_id, user_id))
        row = await cursor.fetchone()
        return dict(row) if row else None

async def mark_auto_word_sent(user_id: int, word_id: int):
    async with get_db_connection() as db:
        await db.execute("UPDATE users SET last_auto_sent_at = CURRENT_TIMESTAMP WHERE user_id = ?", (user_id,))
        await db.execute("""
            UPDATE user_word_progress
            SET last_reviewed_at = CURRENT_TIMESTAMP
            WHERE user_id = ? AND word_id = ?
        """, (user_id, word_id))
        await db.commit()

async def get_auto_quiz_distractors(
    user_id: int,
    current_word_id: int,
    correct_value: str,
    field: str = "translation",
    count: int = 3
) -> List[str]:
    """Fetch distinct distractors for either 'translation' (uz) or 'word' (en)."""
    col = "translation" if field == "translation" else "word"
    correct_norm = (correct_value or "").strip().lower()
    seen = {correct_norm} if correct_norm else set()
    options: List[str] = []

    async with get_db_connection() as db:
        cursor = await db.execute(f"""
            SELECT {col} as val FROM words
            WHERE user_id = ? AND id != ? AND TRIM(COALESCE({col}, '')) != ''
            ORDER BY RANDOM()
            LIMIT 25
        """, (user_id, current_word_id))
        rows = await cursor.fetchall()
        for row in rows:
            val = (row["val"] or "").strip()
            norm = val.lower()
            if val and norm not in seen:
                seen.add(norm)
                options.append(val)
                if len(options) >= count:
                    break

    if len(options) < count:
        fallbacks = (
            ["muhim, ahamiyatli", "qiyin, murakkab", "tez, chaqqon", "yangi, zamonaviy", "ishonchli", "kutilmagan"]
            if col == "translation"
            else ["reluctant", "inevitable", "accurate", "significant", "temporary", "essential"]
        )
        for dummy in fallbacks:
            if len(options) >= count:
                break
            if dummy.lower() not in seen:
                seen.add(dummy.lower())
                options.append(dummy)

    return options[:count]

async def create_auto_challenge(
    user_id: int,
    word_id: int,
    direction: str,
    options: List[str],
    correct_index: int
) -> int:
    async with get_db_connection() as db:
        cursor = await db.execute("""
            INSERT INTO auto_challenges (user_id, word_id, direction, options_json, correct_index)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, word_id, direction, json.dumps(options, ensure_ascii=False), correct_index))
        await db.commit()
        return cursor.lastrowid

async def get_auto_challenge(challenge_id: int, user_id: int) -> Optional[Dict[str, Any]]:
    async with get_db_connection() as db:
        cursor = await db.execute("""
            SELECT * FROM auto_challenges WHERE id = ? AND user_id = ?
        """, (challenge_id, user_id))
        row = await cursor.fetchone()
        if not row:
            return None
        data = dict(row)
        data["options"] = json.loads(data["options_json"])
        return data

async def mark_auto_challenge_answered(challenge_id: int):
    async with get_db_connection() as db:
        await db.execute("UPDATE auto_challenges SET answered = 1 WHERE id = ?", (challenge_id,))
        await db.commit()

# --- API Key Management Queries ---
async def seed_env_keys(gemini_keys: List[str], groq_keys: List[str]):
    async with get_db_connection() as db:
        for k in gemini_keys:
            await db.execute("""
                INSERT OR IGNORE INTO api_keys (provider, api_key, is_active)
                VALUES ('gemini', ?, 1)
            """, (k.strip(),))
        for k in groq_keys:
            await db.execute("""
                INSERT OR IGNORE INTO api_keys (provider, api_key, is_active)
                VALUES ('groq', ?, 1)
            """, (k.strip(),))
        await db.commit()

async def add_api_key(provider: str, api_key: str) -> bool:
    async with get_db_connection() as db:
        try:
            await db.execute("""
                INSERT INTO api_keys (provider, api_key, is_active)
                VALUES (?, ?, 1)
            """, (provider.lower().strip(), api_key.strip()))
            await db.commit()
            return True
        except Exception:
            return False

async def get_api_keys(provider: Optional[str] = None, active_only: bool = False) -> List[Dict[str, Any]]:
    async with get_db_connection() as db:
        query = "SELECT * FROM api_keys WHERE 1=1"
        params: List[Any] = []
        if provider:
            query += " AND provider = ?"
            params.append(provider.lower().strip())
        if active_only:
            query += " AND is_active = 1"
        query += " ORDER BY error_count ASC, usage_count ASC, id ASC"
        
        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

async def delete_api_key(key_id: int) -> bool:
    async with get_db_connection() as db:
        cursor = await db.execute("DELETE FROM api_keys WHERE id = ?", (key_id,))
        await db.commit()
        return cursor.rowcount > 0

async def increment_key_usage(key_id: int):
    async with get_db_connection() as db:
        await db.execute("UPDATE api_keys SET usage_count = usage_count + 1 WHERE id = ?", (key_id,))
        await db.commit()

async def increment_key_error(key_id: int):
    async with get_db_connection() as db:
        await db.execute("UPDATE api_keys SET error_count = error_count + 1 WHERE id = ?", (key_id,))
        await db.commit()

async def reset_key_errors(key_id: int):
    async with get_db_connection() as db:
        await db.execute("UPDATE api_keys SET error_count = 0, is_active = 1 WHERE id = ?", (key_id,))
        await db.commit()

# --- Unit Queries ---
async def create_unit(user_id: int, name: str) -> int:
    async with get_db_connection() as db:
        cursor = await db.execute("""
            INSERT INTO units (user_id, name)
            VALUES (?, ?)
        """, (user_id, name))
        await db.commit()
        return cursor.lastrowid

async def get_user_units(user_id: int) -> List[Dict[str, Any]]:
    async with get_db_connection() as db:
        cursor = await db.execute("""
            SELECT u.id, u.name, u.created_at,
                   COUNT(w.id) as word_count,
                   SUM(CASE WHEN p.status = 'mastered' THEN 1 ELSE 0 END) as mastered_count,
                   SUM(CASE WHEN p.status = 'unknown' THEN 1 ELSE 0 END) as unknown_count
            FROM units u
            LEFT JOIN words w ON w.unit_id = u.id
            LEFT JOIN user_word_progress p ON p.word_id = w.id AND p.user_id = u.user_id
            WHERE u.user_id = ?
            GROUP BY u.id
            ORDER BY u.id DESC
        """, (user_id,))
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

async def get_unit(unit_id: int, user_id: int) -> Optional[Dict[str, Any]]:
    async with get_db_connection() as db:
        cursor = await db.execute("""
            SELECT * FROM units WHERE id = ? AND user_id = ?
        """, (unit_id, user_id))
        row = await cursor.fetchone()
        return dict(row) if row else None

async def delete_unit(unit_id: int, user_id: int):
    async with get_db_connection() as db:
        await db.execute("DELETE FROM units WHERE id = ? AND user_id = ?", (unit_id, user_id))
        await db.commit()

# --- Word Queries ---
async def add_words_bulk(unit_id: int, user_id: int, words: List[Dict[str, Any]]) -> int:
    async with get_db_connection() as db:
        inserted_count = 0
        for item in words:
            word = item.get("word", "").strip()
            if not word:
                continue
            cursor = await db.execute("""
                INSERT INTO words (unit_id, user_id, word, transcription, uz_pronunciation, part_of_speech, translation, example_en, example_uz)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                unit_id,
                user_id,
                word,
                item.get("transcription", ""),
                item.get("uz_pronunciation", ""),
                item.get("part_of_speech", ""),
                item.get("translation", ""),
                item.get("example_en", ""),
                item.get("example_uz", "")
            ))
            word_id = cursor.lastrowid
            
            await db.execute("""
                INSERT OR IGNORE INTO user_word_progress (user_id, word_id, status)
                VALUES (?, ?, 'learning')
            """, (user_id, word_id))
            inserted_count += 1
            
        await db.commit()
        return inserted_count

async def get_words_by_unit(unit_id: int, user_id: int, status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
    async with get_db_connection() as db:
        query = """
            SELECT w.*, COALESCE(p.status, 'learning') as status,
                   COALESCE(p.correct_count, 0) as correct_count,
                   COALESCE(p.incorrect_count, 0) as incorrect_count
            FROM words w
            LEFT JOIN user_word_progress p ON p.word_id = w.id AND p.user_id = w.user_id
            WHERE w.unit_id = ? AND w.user_id = ?
        """
        params: List[Any] = [unit_id, user_id]
        if status_filter:
            query += " AND p.status = ?"
            params.append(status_filter)
            
        query += " ORDER BY w.id ASC"
        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

async def get_word_by_id(word_id: int, user_id: int) -> Optional[Dict[str, Any]]:
    async with get_db_connection() as db:
        cursor = await db.execute("""
            SELECT w.*, un.name as unit_name
            FROM words w
            LEFT JOIN units un ON un.id = w.unit_id
            WHERE w.id = ? AND w.user_id = ?
        """, (word_id, user_id))
        row = await cursor.fetchone()
        return dict(row) if row else None

async def get_practice_words(user_id: int, unit_id: Optional[int] = None, status_filter: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
    async with get_db_connection() as db:
        query = """
            SELECT w.*, COALESCE(p.status, 'learning') as status,
                   COALESCE(p.correct_count, 0) as correct_count,
                   COALESCE(p.incorrect_count, 0) as incorrect_count
            FROM words w
            LEFT JOIN user_word_progress p ON p.word_id = w.id AND p.user_id = w.user_id
            WHERE w.user_id = ?
        """
        params: List[Any] = [user_id]
        if unit_id is not None:
            query += " AND w.unit_id = ?"
            params.append(unit_id)
        if status_filter:
            query += " AND p.status = ?"
            params.append(status_filter)
            
        query += """
            ORDER BY 
                CASE COALESCE(p.status, 'learning')
                    WHEN 'unknown' THEN 1
                    WHEN 'learning' THEN 2
                    WHEN 'mastered' THEN 3
                    ELSE 4
                END,
                RANDOM()
            LIMIT ?
        """
        params.append(limit)
        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

async def get_random_distractors(user_id: int, current_word_id: int, count: int = 3) -> List[str]:
    async with get_db_connection() as db:
        cursor = await db.execute("""
            SELECT translation FROM words 
            WHERE user_id = ? AND id != ?
            ORDER BY RANDOM()
            LIMIT ?
        """, (user_id, current_word_id, count))
        rows = await cursor.fetchall()
        options = [row["translation"] for row in rows]
        
        dummy_distractors = ["muhim, ahamiyatli", "qiyin, murakkab", "tez, chaqqon", "yangi, zamonaviy", "chiroyli, ajoyib", "kutilmagan"]
        for dummy in dummy_distractors:
            if len(options) >= count:
                break
            if dummy not in options:
                options.append(dummy)
        return options[:count]

# --- Progress & Spaced Repetition Queries ---
async def record_answer(user_id: int, word_id: int, is_correct: bool) -> str:
    async with get_db_connection() as db:
        cursor = await db.execute("""
            SELECT correct_count, incorrect_count, status 
            FROM user_word_progress 
            WHERE user_id = ? AND word_id = ?
        """, (user_id, word_id))
        row = await cursor.fetchone()
        
        correct_count = 0
        incorrect_count = 0
        if row:
            correct_count = row["correct_count"]
            incorrect_count = row["incorrect_count"]
            
        if is_correct:
            correct_count += 1
            new_status = "mastered" if correct_count >= 3 else "learning"
        else:
            incorrect_count += 1
            correct_count = max(0, correct_count - 1)
            new_status = "unknown"
            
        await db.execute("""
            INSERT INTO user_word_progress (user_id, word_id, correct_count, incorrect_count, status, last_reviewed_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id, word_id) DO UPDATE SET
                correct_count = excluded.correct_count,
                incorrect_count = excluded.incorrect_count,
                status = excluded.status,
                last_reviewed_at = CURRENT_TIMESTAMP;
        """, (user_id, word_id, correct_count, incorrect_count, new_status))
        await db.commit()
        return new_status

async def get_user_stats(user_id: int) -> Dict[str, int]:
    async with get_db_connection() as db:
        cursor = await db.execute("""
            SELECT 
                COUNT(w.id) as total_words,
                SUM(CASE WHEN p.status = 'mastered' THEN 1 ELSE 0 END) as mastered_words,
                SUM(CASE WHEN p.status = 'unknown' THEN 1 ELSE 0 END) as unknown_words,
                SUM(CASE WHEN COALESCE(p.status, 'learning') = 'learning' THEN 1 ELSE 0 END) as learning_words
            FROM words w
            LEFT JOIN user_word_progress p ON p.word_id = w.id AND p.user_id = w.user_id
            WHERE w.user_id = ?
        """, (user_id,))
        row = await cursor.fetchone()
        if not row:
            return {"total_words": 0, "mastered_words": 0, "unknown_words": 0, "learning_words": 0}
        return {
            "total_words": row["total_words"] or 0,
            "mastered_words": row["mastered_words"] or 0,
            "unknown_words": row["unknown_words"] or 0,
            "learning_words": row["learning_words"] or 0,
        }
