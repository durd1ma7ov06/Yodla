import json
import logging
from typing import List, Dict, Any
from google import genai
from google.genai import types
import asyncio

from config import GEMINI_API_KEY, GROQ_API_KEY

logger = logging.getLogger(__name__)

# Ordered list of active vision & text models for automatic fallback
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
    
    # Handle cases where model puts preamble before '['
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

def _sync_extract_image(image_bytes: bytes) -> List[Dict[str, Any]]:
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY sozlanmagan!")
    
    client = genai.Client(api_key=GEMINI_API_KEY)
    prompt = (
        SYSTEM_PROMPT + "\n\n"
        "Carefully read all vocabulary words from this textbook page or image. "
        "Extract every distinct word or phrase, their IPA transcriptions, parts of speech, "
        "accurate Uzbek translations, and create example sentences. "
        "Return pure JSON list."
    )
    
    image_part = types.Part.from_bytes(
        data=image_bytes,
        mime_type="image/jpeg"
    )
    
    last_error = None
    for model_name in GEMINI_MODELS:
        try:
            logger.info(f"Trying image extraction with model: {model_name}")
            response = client.models.generate_content(
                model=model_name,
                contents=[prompt, image_part]
            )
            return clean_json_response(response.text)
        except Exception as e:
            logger.warning(f"Model {model_name} failed for image: {e}")
            last_error = e
            continue

    raise ValueError(f"AI rasmdan so'zlarni o'qiy olmadi (server band). Qayta urinib ko'ring. Tafsilot: {last_error}")

def _sync_extract_text(user_text: str) -> List[Dict[str, Any]]:
    # 1. Try Gemini models
    if GEMINI_API_KEY:
        client = genai.Client(api_key=GEMINI_API_KEY)
        prompt = (
            SYSTEM_PROMPT + "\n\n"
            f"Input text provided by user:\n\"\"\"{user_text}\"\"\"\n\n"
            "Extract the vocabulary words/expressions from this input. If the user provided translations, respect and refine them into standard Uzbek. "
            "If only words are provided, find their accurate Uzbek translations, IPA transcriptions, parts of speech, and example sentences. "
            "Return pure JSON list."
        )
        for model_name in GEMINI_MODELS:
            try:
                logger.info(f"Trying text extraction with Gemini: {model_name}")
                response = client.models.generate_content(
                    model=model_name,
                    contents=[prompt]
                )
                return clean_json_response(response.text)
            except Exception as e:
                logger.warning(f"Gemini {model_name} failed: {e}")
                continue

    # 2. Fallback to Groq models
    if GROQ_API_KEY:
        from groq import Groq
        groq_client = Groq(api_key=GROQ_API_KEY)
        prompt = (
            SYSTEM_PROMPT + "\n\n"
            f"Input text provided by user:\n\"\"\"{user_text}\"\"\"\n\n"
            "Extract the vocabulary words/expressions. Return pure JSON array."
        )
        for gm in GROQ_MODELS:
            try:
                logger.info(f"Trying text extraction with Groq: {gm}")
                chat_completion = groq_client.chat.completions.create(
                    model=gm,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=900,
                    temperature=0.2
                )
                content = chat_completion.choices[0].message.content
                return clean_json_response(content)
            except Exception as ge:
                logger.warning(f"Groq {gm} failed: {ge}")
                continue

    raise ValueError("Hech qanday AI servisi javob bermadi. Birozdan so'ng qayta urinib ko'ring.")

async def extract_words_from_image(image_bytes: bytes) -> List[Dict[str, Any]]:
    """Extract vocabulary from image using Gemini Vision with multi-model fallback."""
    return await asyncio.to_thread(_sync_extract_image, image_bytes)

async def extract_words_from_text(user_text: str) -> List[Dict[str, Any]]:
    """Extract and analyze vocabulary from text with multi-model & Groq fallback."""
    return await asyncio.to_thread(_sync_extract_text, user_text)
