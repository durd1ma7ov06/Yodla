import json
import logging
from typing import List, Dict, Any, Tuple
from google import genai
from google.genai import types
import asyncio

from config import GEMINI_API_KEYS, GROQ_API_KEYS
from database.queries import get_api_keys, increment_key_usage, increment_key_error

logger = logging.getLogger(__name__)

GEMINI_MODELS = [
    "gemini-3.5-flash",
    "gemini-3.1-flash-lite",
    "gemini-3.6-flash",
    "gemini-3.5-flash-lite",
    "gemma-4-26b-a4b-it",
]

GROQ_MODELS = [
    "qwen/qwen3.8-27b",
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b"
]

SYSTEM_PROMPT = """
You are an expert English-to-Uzbek lexicographer and language teacher.
Your task is to extract or analyze English vocabulary words from the provided image or text and return structured dictionary data in Uzbek.

Instructions:
1. Extract or parse the English words.
2. For each word, provide:
   - "word": The English word in base/lemma form (lowercase).
   - "transcription": IPA phonetic transcription (e.g. "/ˌæk.sɪˈdent/").
   - "part_of_speech": The part of speech in English (e.g. "noun", "verb", "adjective", "adverb", "phrasal verb").
   - "translation": Natural and accurate Uzbek translation(s) commonly used in Uzbekistan (Latin alphabet).
   - "example_en": A clear, practical example sentence using the word.
   - "example_uz": Accurate Uzbek translation of that example sentence.
3. Return ONLY a valid JSON array of objects. Do NOT include markdown code blocks (like ```json), commentary, or extra text.
"""

def clean_json_response(raw_text: str) -> List[Dict[str, Any]]:
    text = raw_text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()
    
    start_idx = text.find("[")
    end_idx = text.rfind("]")
    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        text = text[start_idx:end_idx + 1]
    
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
        elif isinstance(data, dict) and "words" in data and isinstance(data["words"], list):
            return data["words"]
        elif isinstance(data, dict):
            return [data]
        return []
    except Exception as e:
        logger.error(f"JSON parsing error: {e}, Raw text: {text[:200]}")
        raise ValueError("AI javobini JSON formatida o'qib bo'lmadi. Qaytadan urinib ko'ring.")

def _sync_call_gemini_image(api_key: str, image_bytes: bytes) -> Tuple[bool, Any]:
    client = genai.Client(api_key=api_key)
    prompt = (
        SYSTEM_PROMPT + "\n\n"
        "Carefully read all vocabulary words from this textbook page or image. "
        "Extract every distinct word or phrase, their IPA transcriptions, parts of speech, "
        "accurate Uzbek translations, and create example sentences. "
        "Return pure JSON list."
    )
    image_part = types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg")
    
    last_err = None
    for model_name in GEMINI_MODELS:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=[prompt, image_part]
            )
            return True, clean_json_response(response.text)
        except Exception as e:
            logger.warning(f"Gemini image ({model_name}) failed: {e}")
            last_err = e
            # If invalid key error (400/401/403), break out to try next API key immediately
            if "API_KEY_INVALID" in str(e) or "403" in str(e) or "401" in str(e):
                break
            continue
    return False, last_err

def _sync_call_gemini_text(api_key: str, user_text: str) -> Tuple[bool, Any]:
    client = genai.Client(api_key=api_key)
    prompt = (
        SYSTEM_PROMPT + "\n\n"
        f"Input text provided by user:\n\"\"\"{user_text}\"\"\"\n\n"
        "Extract the vocabulary words/expressions from this input. If the user provided translations, respect and refine them into standard Uzbek. "
        "If only words are provided, find their accurate Uzbek translations, IPA transcriptions, parts of speech, and example sentences. "
        "Return pure JSON list."
    )
    last_err = None
    for model_name in GEMINI_MODELS:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=[prompt]
            )
            return True, clean_json_response(response.text)
        except Exception as e:
            logger.warning(f"Gemini text ({model_name}) failed: {e}")
            last_err = e
            if "API_KEY_INVALID" in str(e) or "403" in str(e) or "401" in str(e):
                break
            continue
    return False, last_err

def _sync_call_groq_text(api_key: str, user_text: str) -> Tuple[bool, Any]:
    from groq import Groq
    groq_client = Groq(api_key=api_key)
    prompt = (
        SYSTEM_PROMPT + "\n\n"
        f"Input text provided by user:\n\"\"\"{user_text}\"\"\"\n\n"
        "Extract the vocabulary words/expressions. Return pure JSON array."
    )
    last_err = None
    for gm in GROQ_MODELS:
        try:
            chat_completion = groq_client.chat.completions.create(
                model=gm,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=900,
                temperature=0.2
            )
            return True, clean_json_response(chat_completion.choices[0].message.content)
        except Exception as e:
            logger.warning(f"Groq ({gm}) failed: {e}")
            last_err = e
            if "invalid_api_key" in str(e).lower() or "401" in str(e):
                break
            continue
    return False, last_err

async def _get_provider_keys(provider: str) -> List[Dict[str, Any]]:
    db_keys = await get_api_keys(provider=provider, active_only=True)
    if db_keys:
        return db_keys
    # Fallback to env keys if DB empty
    fallback = GEMINI_API_KEYS if provider == "gemini" else GROQ_API_KEYS
    return [{"id": None, "api_key": k} for k in fallback]

async def extract_words_from_image(image_bytes: bytes) -> List[Dict[str, Any]]:
    keys = await _get_provider_keys("gemini")
    if not keys:
        raise ValueError("Hech qanday GEMINI API kaliti mavjud emas! /admin paneldan qo'shing.")
        
    last_error = None
    for k_row in keys:
        success, result = await asyncio.to_thread(_sync_call_gemini_image, k_row["api_key"], image_bytes)
        if success:
            if k_row["id"]:
                await increment_key_usage(k_row["id"])
            return result
        else:
            last_error = result
            if k_row["id"]:
                await increment_key_error(k_row["id"])
                
    raise ValueError(f"Barcha Gemini kalitlarida xatolik yuz berdi: {last_error}")

async def extract_words_from_text(user_text: str) -> List[Dict[str, Any]]:
    # 1. Try all Gemini keys
    gemini_keys = await _get_provider_keys("gemini")
    for k_row in gemini_keys:
        success, result = await asyncio.to_thread(_sync_call_gemini_text, k_row["api_key"], user_text)
        if success:
            if k_row["id"]:
                await increment_key_usage(k_row["id"])
            return result
        else:
            if k_row["id"]:
                await increment_key_error(k_row["id"])

    # 2. Fallback to all Groq keys
    groq_keys = await _get_provider_keys("groq")
    for k_row in groq_keys:
        success, result = await asyncio.to_thread(_sync_call_groq_text, k_row["api_key"], user_text)
        if success:
            if k_row["id"]:
                await increment_key_usage(k_row["id"])
            return result
        else:
            if k_row["id"]:
                await increment_key_error(k_row["id"])

    raise ValueError("Barcha Gemini va Groq API kalitlarida muammo yuz berdi. /admin orqali yangi kalit qo'shing.")

def _sync_test_key(provider: str, api_key: str) -> Tuple[bool, str]:
    try:
        if provider == "gemini":
            client = genai.Client(api_key=api_key)
            for m in ["gemini-3.5-flash", "gemini-3.1-flash-lite"]:
                try:
                    res = client.models.generate_content(model=m, contents="OK")
                    return True, f"Ishlayapti ({m})"
                except Exception as e:
                    if "API_KEY_INVALID" in str(e) or "403" in str(e):
                        return False, "Kalit yaroqsiz (Invalid API Key)"
                    continue
            return False, "Modellar hozir band (503)"
        elif provider == "groq":
            from groq import Groq
            g = Groq(api_key=api_key)
            res = g.chat.completions.create(
                model="qwen/qwen3.8-27b",
                messages=[{"role": "user", "content": "OK"}],
                max_tokens=10
            )
            return True, "Ishlayapti (Groq Qwen)"
    except Exception as e:
        return False, str(e)[:60]
    return False, "Noma'lum xato"

async def test_api_key_live(provider: str, api_key: str) -> Tuple[bool, str]:
    """Tests if an API key is live and responding."""
    return await asyncio.to_thread(_sync_test_key, provider, api_key)
