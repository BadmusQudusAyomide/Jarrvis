"""Voice endpoints for the desktop app: mic input (STT), spoken replies (TTS),
and always-on wake-word detection ("Hey Jarvis") for hands-free mode."""
import logging
import os
import tempfile
import time

import numpy as np
from fastapi import APIRouter, UploadFile, File, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from pydantic import BaseModel

from app.llm.groq_media import transcribe_audio, synthesize_speech

logger = logging.getLogger(__name__)
router = APIRouter()

# Wake-word detection (openWakeWord, fully offline/local — no account or API key).
# Frame size: openWakeWord expects 16-bit 16kHz mono PCM in multiples of 80ms
# (1280 samples = 2560 bytes per frame).
WAKEWORD_FRAME_SAMPLES = 1280
WAKEWORD_THRESHOLD = 0.5
WAKEWORD_COOLDOWN_SECONDS = 2.0

_wakeword_model = None


def _get_wakeword_model():
    global _wakeword_model
    if _wakeword_model is None:
        from openwakeword.model import Model
        logger.info("Loading openWakeWord 'hey_jarvis' model...")
        _wakeword_model = Model(wakeword_models=["hey_jarvis"], inference_framework="onnx")
    return _wakeword_model


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


@router.websocket("/voice/wakeword")
async def voice_wakeword(websocket: WebSocket):
    """Streaming wake-word detection. Client sends raw 16-bit 16kHz mono PCM
    audio chunks as binary WebSocket frames; server replies {"detected": true}
    whenever "hey jarvis" is heard, at most once per cooldown window."""
    await websocket.accept()
    model = _get_wakeword_model()
    frame_bytes = WAKEWORD_FRAME_SAMPLES * 2  # int16 = 2 bytes/sample
    buffer = bytearray()
    last_trigger = 0.0

    try:
        while True:
            chunk = await websocket.receive_bytes()
            buffer.extend(chunk)

            while len(buffer) >= frame_bytes:
                frame_data = bytes(buffer[:frame_bytes])
                del buffer[:frame_bytes]

                frame = np.frombuffer(frame_data, dtype=np.int16)
                prediction = model.predict(frame)
                score = prediction.get("hey_jarvis", 0.0)

                now = time.monotonic()
                if score > WAKEWORD_THRESHOLD and (now - last_trigger) > WAKEWORD_COOLDOWN_SECONDS:
                    last_trigger = now
                    logger.info(f"Wake word detected (score={score:.2f})")
                    await websocket.send_json({"detected": True, "score": float(score)})
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"voice_wakeword error: {e}", exc_info=True)
