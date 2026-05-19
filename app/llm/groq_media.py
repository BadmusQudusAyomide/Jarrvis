"""Groq cloud API for audio transcription (Whisper) and image analysis (Vision).
Used by the Telegram bot for voice notes and photo messages.
Falls back gracefully when GROQ_API_KEY is not set.
"""
import os
import base64
import requests
import logging

logger = logging.getLogger(__name__)

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_WHISPER_MODEL = os.getenv("GROQ_WHISPER_MODEL", "whisper-large-v3")
GROQ_VISION_MODEL = os.getenv("GROQ_VISION_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")


def transcribe_audio(audio_path: str) -> str:
    """Transcribe an audio file using Groq Whisper API. Returns plain text."""
    if not GROQ_API_KEY:
        return "Error: GROQ_API_KEY not set — cannot transcribe audio."

    url = "https://api.groq.com/openai/v1/audio/transcriptions"
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}"}

    try:
        with open(audio_path, "rb") as f:
            files = {"file": (os.path.basename(audio_path), f, "audio/ogg")}
            data = {"model": GROQ_WHISPER_MODEL, "response_format": "text"}
            resp = requests.post(url, headers=headers, files=files, data=data, timeout=60)

        if resp.status_code != 200:
            logger.error(f"Whisper API {resp.status_code}: {resp.text[:200]}")
            return f"Transcription failed (HTTP {resp.status_code})"

        return resp.text.strip()
    except Exception as e:
        logger.error(f"transcribe_audio error: {e}")
        return f"Transcription error: {e}"


def analyze_image(image_path: str, prompt: str = "Describe this image in detail. What do you see?") -> str:
    """Analyze an image using Groq Vision API. Returns a text description."""
    if not GROQ_API_KEY:
        return "Error: GROQ_API_KEY not set — cannot analyze image."

    ext = os.path.splitext(image_path)[1].lower()
    mime = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}.get(ext, "image/jpeg")

    try:
        with open(image_path, "rb") as f:
            image_b64 = base64.b64encode(f.read()).decode("utf-8")

        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
        payload = {
            "model": GROQ_VISION_MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{image_b64}"}},
                    ],
                }
            ],
            "max_tokens": 1024,
        }

        resp = requests.post(url, json=payload, headers=headers, timeout=60)
        if resp.status_code != 200:
            logger.error(f"Vision API {resp.status_code}: {resp.text[:200]}")
            return f"Image analysis failed (HTTP {resp.status_code})"

        return resp.json().get("choices", [{}])[0].get("message", {}).get("content", "").strip()
    except Exception as e:
        logger.error(f"analyze_image error: {e}")
        return f"Image analysis error: {e}"
