import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env", override=True)

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", "6956456422").strip())
DATABASE_PATH = BASE_DIR / os.getenv("DATABASE_PATH", "data/lugat.db")

DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
