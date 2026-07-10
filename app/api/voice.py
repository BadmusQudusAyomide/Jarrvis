"""Voice endpoints for the desktop app: mic input (STT) and spoken replies (TTS)."""
import logging
import os
import tempfile

from fastapi import APIRouter, UploadFile, File
from fastapi.responses import Response
from pydantic import BaseModel

from app.llm.groq_media import transcribe_audio, synthesize_speech

logger = logging.getLogger(__name__)
router = APIRouter()


class SpeakRequest(BaseModel):
    text: str
    voice: str | None = None


@router.post("/voice/transcribe")
async def voice_transcribe(file: UploadFile = File(...)):
    """Transcribe an uploaded audio clip (e.g. recorded from the browser mic) to text."""
    suffix = os.path.splitext(file.filename or "")[1] or ".webm"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp_path = tmp.name
        tmp.write(await file.read())

    try:
        text = transcribe_audio(tmp_path)
        if text.lower().startswith("error") or "failed" in text.lower():
            return {"text": "", "error": text}
        return {"text": text}
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


@router.post("/voice/speak")
async def voice_speak(req: SpeakRequest):
    """Synthesize speech for the given text, returning raw WAV audio."""
    try:
        audio_bytes = synthesize_speech(req.text, voice=req.voice)
        return Response(content=audio_bytes, media_type="audio/wav")
    except RuntimeError as e:
        logger.error(f"voice_speak failed: {e}")
        return Response(content=str(e), status_code=502, media_type="text/plain")
