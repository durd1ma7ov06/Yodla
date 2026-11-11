import io
from gtts import gTTS
import asyncio

async def generate_speech_bytes(text: str, lang: str = "en") -> io.BytesIO:
    """Generate pronunciation MP3 audio buffer using gTTS asynchronously."""
    def _create_tts():
        fp = io.BytesIO()
        tts = gTTS(text=text, lang=lang, slow=False)
        tts.write_to_fp(fp)
        fp.seek(0)
        return fp

    return await asyncio.to_thread(_create_tts)
