"""WhatsApp Cloud API webhook — receives messages, replies via Jarvis's chat pipeline.

Mirrors interfaces/telegram/bot.py's pattern (one session per sender, talks to
the internal /chat endpoint) but is webhook-driven instead of polling-driven,
since that's how the Cloud API delivers messages.
"""
import asyncio
import hashlib
import hmac
import json
import logging
import os

import requests
from fastapi import APIRouter, Request, Response

logger = logging.getLogger(__name__)
router = APIRouter()

WHATSAPP_ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN", "").strip()
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "").strip()
WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "").strip()
WHATSAPP_APP_SECRET = os.getenv("WHATSAPP_APP_SECRET", "").strip()
# Set to your own WhatsApp number (digits only, e.g. 2348012345678) to restrict
# the bot to just you — leave empty to allow anyone who messages the number.
OWNER_WHATSAPP_NUMBER = os.getenv("OWNER_WHATSAPP_NUMBER", "").strip()

GRAPH_API_VERSION = "v20.0"

_PORT = os.getenv("PORT", "8080")
_CHAT_API_URL = f"http://127.0.0.1:{_PORT}/chat"


def _session_id(phone_number: str) -> str:
    return f"whatsapp_{phone_number}"


def _verify_signature(body: bytes, signature_header: str) -> bool:
    """Confirm the webhook payload really came from Meta, not a forged request."""
    if not WHATSAPP_APP_SECRET:
        # No app secret configured — skip verification (fine for early testing,
        # but set WHATSAPP_APP_SECRET before relying on this for anything real).
        return True
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(WHATSAPP_APP_SECRET.encode(), body, hashlib.sha256).hexdigest()
    provided = signature_header.split("=", 1)[1]
    return hmac.compare_digest(expected, provided)


def _send_whatsapp_message(to: str, text: str):
    if not WHATSAPP_ACCESS_TOKEN or not WHATSAPP_PHONE_NUMBER_ID:
        logger.warning("WhatsApp not configured (missing access token / phone number id) — cannot send reply")
        return
    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}", "Content-Type": "application/json"}
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text[:4096]},  # WhatsApp caps text message bodies at 4096 chars
    }
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        if resp.status_code >= 400:
            logger.error(f"WhatsApp send failed: {resp.status_code} {resp.text}")
    except Exception as e:
        logger.error(f"WhatsApp send error: {e}")


def _ask_jarvis(message: str, session_id: str) -> str:
    try:
        resp = requests.post(_CHAT_API_URL, json={"message": message, "session_id": session_id}, timeout=300)
        resp.raise_for_status()
        payload = resp.json().get("response", "No response")
        if isinstance(payload, (dict, list)):
            return json.dumps(payload, ensure_ascii=False)
        return str(payload)
    except requests.Timeout:
        return "That's taking a while — the operation may still be running, try asking again shortly."
    except Exception as e:
        logger.error(f"ask_jarvis error: {e}")
        return f"Error: {e}"


def _extract_incoming_text_message(payload: dict):
    """Pull (from_number, text) out of a Cloud API webhook payload, or None
    if this isn't a user text message (e.g. a delivery/read status callback)."""
    try:
        value = payload["entry"][0]["changes"][0]["value"]
        messages = value.get("messages")
        if not messages:
            return None
        message = messages[0]
        from_number = message.get("from")
        if message.get("type") != "text":
            return from_number, None
        return from_number, message.get("text", {}).get("body", "")
    except (KeyError, IndexError, TypeError):
        return None


async def _handle_incoming_message(from_number: str, text: str):
    """Runs in the background so the webhook can ack Meta immediately —
    Meta expects a fast 200 and will retry (re-delivering the same message)
    if we're slow, and the agent loop can take a while."""
    if OWNER_WHATSAPP_NUMBER and from_number != OWNER_WHATSAPP_NUMBER:
        logger.warning(f"Ignoring WhatsApp message from non-owner number: {from_number}")
        return

    if not text:
        await asyncio.to_thread(_send_whatsapp_message, from_number, "I can only handle text messages on WhatsApp right now.")
        return

    session_id = _session_id(from_number)
    reply = await asyncio.to_thread(_ask_jarvis, text, session_id)
    await asyncio.to_thread(_send_whatsapp_message, from_number, reply)


@router.get("/whatsapp/webhook")
def verify_webhook(request: Request):
    """Meta's one-time webhook verification handshake — called when you save
    the webhook URL in the Meta dashboard."""
    params = request.query_params
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    if mode == "subscribe" and WHATSAPP_VERIFY_TOKEN and token == WHATSAPP_VERIFY_TOKEN:
        return Response(content=challenge or "", media_type="text/plain")
    return Response(content="Forbidden", status_code=403)


@router.post("/whatsapp/webhook")
async def receive_webhook(request: Request):
    """Receives incoming WhatsApp messages and replies via the Jarvis chat pipeline."""
    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")
    if not _verify_signature(body, signature):
        logger.warning("WhatsApp webhook signature verification failed")
        return Response(status_code=403)

    try:
        payload = json.loads(body or b"{}")
    except json.JSONDecodeError:
        return Response(status_code=400)

    parsed = _extract_incoming_text_message(payload)
    if parsed:
        from_number, text = parsed
        asyncio.create_task(_handle_incoming_message(from_number, text))

    return {"status": "ok"}
