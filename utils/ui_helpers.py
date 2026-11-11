from typing import Dict, Any

def progress_bar(current: int, total: int, length: int = 8) -> str:
    """Generate visual progress bar like [🟩🟩🟩⬜⬜⬜⬜⬜]."""
    if total <= 0:
        return "⬜" * length
    filled = min(length, round((current / total) * length))
    return "🟩" * filled + "⬜" * (length - filled)

def format_word_card(word_dict: Dict[str, Any], index: int = 1) -> str:
    """Format single vocabulary word in clean card layout."""
    status = word_dict.get("status", "learning")
    badge = "🟢 Yodlangan" if status == "mastered" else ("🔴 Qiyin so'z" if status == "unknown" else "🟡 O'rganilmoqda")
    
    word = word_dict.get("word", "").upper()
    transcription = f" [<code>{word_dict.get('transcription', '')}</code>]" if word_dict.get("transcription") else ""
    pos = f" <i>({word_dict.get('part_of_speech', '')})</i>" if word_dict.get("part_of_speech") else ""
    translation = word_dict.get("translation", "")
    
    text = (
        f"<b>{index}. {word}</b>{pos}{transcription} — <b>{badge}</b>\n"
        f"   🇺🇿 {translation}\n"
    )
    if word_dict.get("example_en"):
        text += f"   💬 <i>\"{word_dict['example_en']}\"</i>\n"
    return text
