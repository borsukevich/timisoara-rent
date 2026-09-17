from curl_cffi import requests
import logging

logger = logging.getLogger("Translator")

def translate_to_russian(text: str, max_chars: int = 500) -> str:
    """Translates Romanian real estate text to Russian using free Google endpoint."""
    if not text:
        return ""
    clean_text = text.strip()
    if len(clean_text) > max_chars:
        clean_text = clean_text[:max_chars].strip()

    try:
        url = "https://translate.googleapis.com/translate_a/single"
        params = {
            "client": "gtx",
            "sl": "ro",
            "tl": "ru",
            "dt": "t",
            "q": clean_text
        }
        r = requests.get(url, params=params, impersonate="chrome124", timeout=10)
        if r.status_code == 200:
            res = r.json()
            if res and isinstance(res, list) and len(res) > 0 and isinstance(res[0], list):
                translated = "".join(part[0] for part in res[0] if part and part[0])
                return translated.strip()
    except Exception as e:
        logger.warning(f"Translation error: {e}")

    # Fallback to original text if translation fails
    return clean_text

