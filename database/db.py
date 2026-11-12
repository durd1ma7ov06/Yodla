import aiosqlite
from contextlib import asynccontextmanager
from config import DATABASE_PATH

@asynccontextmanager
async def get_db_connection():
    """Async context manager for SQLite database connection."""
    async with aiosqlite.connect(DATABASE_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys = ON;")
        yield conn

async def init_db():
    async with get_db_connection() as db:
        # 1. Foydalanuvchilar
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                language_code TEXT,
                is_premium INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_active_at TIMESTAMP
            );
        """)

        for col, col_type in [("language_code", "TEXT"), ("is_premium", "INTEGER DEFAULT 0"), ("last_active_at", "TIMESTAMP")]:
            try:
                await db.execute(f"ALTER TABLE users ADD COLUMN {col} {col_type};")
            except Exception:
                pass

        # 2. Unitlar / To'plamlar
        await db.execute("""
            CREATE TABLE IF NOT EXISTS units (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            );
        """)

        # 3. So'zlar
        await db.execute("""
            CREATE TABLE IF NOT EXISTS words (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                unit_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                word TEXT NOT NULL,
                transcription TEXT,
                part_of_speech TEXT,
                translation TEXT NOT NULL,
                example_en TEXT,
                example_uz TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (unit_id) REFERENCES units(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            );
        """)

        # 4. Bilgan/Bilmagan holati
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_word_progress (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                word_id INTEGER NOT NULL,
                correct_count INTEGER DEFAULT 0,
                incorrect_count INTEGER DEFAULT 0,
                status TEXT DEFAULT 'learning',
                last_reviewed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, word_id),
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                FOREIGN KEY (word_id) REFERENCES words(id) ON DELETE CASCADE
            );
        """)

        # 5. API Kalitlar (Multi-key Rotation & Admin Management)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS api_keys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider TEXT NOT NULL,
                api_key TEXT NOT NULL UNIQUE,
                is_active INTEGER DEFAULT 1,
                usage_count INTEGER DEFAULT 0,
                error_count INTEGER DEFAULT 0,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        await db.commit()
