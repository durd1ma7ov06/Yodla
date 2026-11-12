import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env", override=True)

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

def _parse_keys(env_name: str) -> list[str]:
    raw = os.getenv(env_name, "").strip()
    if not raw:
        return []
    return [k.strip() for k in raw.split(",") if k.strip()]

GEMINI_API_KEYS = _parse_keys("GEMINI_API_KEY")
GROQ_API_KEYS = _parse_keys("GROQ_API_KEY")

GEMINI_API_KEY = GEMINI_API_KEYS[0] if GEMINI_API_KEYS else ""
GROQ_API_KEY = GROQ_API_KEYS[0] if GROQ_API_KEYS else ""

ADMIN_ID = int(os.getenv("ADMIN_ID", "6956456422").strip())
DATABASE_PATH = BASE_DIR / os.getenv("DATABASE_PATH", "data/lugat.db")

DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
