import json
import logging
from typing import List, Dict, Any
from google import genai
from google.genai import types
import asyncio

from config import GEMINI_API_KEY, GROQ_API_KEY

logger = logging.getLogger(__name__)

# Active fast multimodal model
GEMINI_MODEL = "gemini-3.1-flash-lite"

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
    
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=[prompt, image_part]
    )
    return clean_json_response(response.text)

def _sync_extract_text(user_text: str) -> List[Dict[str, Any]]:
    # Try Gemini first
    if GEMINI_API_KEY:
        try:
            client = genai.Client(api_key=GEMINI_API_KEY)
            prompt = (
                SYSTEM_PROMPT + "\n\n"
                f"Input text provided by user:\n\"\"\"{user_text}\"\"\"\n\n"
                "Extract the vocabulary words/expressions from this input. If the user provided translations, respect and refine them into standard Uzbek. "
                "If only words are provided, find their accurate Uzbek translations, IPA transcriptions, parts of speech, and example sentences. "
                "Return pure JSON list."
            )
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=[prompt]
            )
            return clean_json_response(response.text)
        except Exception as e:
            logger.warning(f"Gemini text extraction failed: {e}. Trying Groq fallback...")

    # Fallback to Groq
    if GROQ_API_KEY:
        try:
            from groq import Groq
            groq_client = Groq(api_key=GROQ_API_KEY)
            prompt = (
                SYSTEM_PROMPT + "\n\n"
                f"Input text provided by user:\n\"\"\"{user_text}\"\"\"\n\n"
                "Extract the vocabulary words/expressions. Return pure JSON array."
            )
            chat_completion = groq_client.chat.completions.create(
                model="qwen/qwen3.8-27b",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=900,
                temperature=0.2
            )
            content = chat_completion.choices[0].message.content
            return clean_json_response(content)
        except Exception as ge:
            logger.error(f"Groq fallback failed: {ge}")
            raise ge

    raise ValueError("Hech qanday AI servisi ishlamadi.")

async def extract_words_from_image(image_bytes: bytes) -> List[Dict[str, Any]]:
    """Extract vocabulary from image using Gemini Vision asynchronously."""
    return await asyncio.to_thread(_sync_extract_image, image_bytes)

async def extract_words_from_text(user_text: str) -> List[Dict[str, Any]]:
    """Extract and analyze vocabulary from text asynchronously."""
    return await asyncio.to_thread(_sync_extract_text, user_text)
