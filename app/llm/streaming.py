"""Streaming support for Ollama responses."""
import requests
import json
import logging
from app.config import OLLAMA_URL, DEFAULT_MODEL, SYSTEM_PROMPT

logger = logging.getLogger(__name__)
TIMEOUT = 300  # seconds for streaming (5 minutes for slow models)


def chat_with_ollama_stream(history: list, model: str = None, system_prompt: str = None):
    """Stream conversation history to model, yielding tokens as they arrive."""
    url = f"{OLLAMA_URL}/api/chat"
    
    model_to_use = model or DEFAULT_MODEL
    prompt_to_use = system_prompt or SYSTEM_PROMPT

    messages = [{"role": "system", "content": prompt_to_use}]
    messages.extend(history)

    payload = {
        "model": model_to_use,
        "messages": messages,
        "stream": True
    }

    try:
        with requests.post(url, json=payload, stream=True, timeout=TIMEOUT) as res:
            if res.status_code != 200:
                yield f"Error: HTTP {res.status_code}"
                return

            for line in res.iter_lines():
                if line:
                    try:
                        data = json.loads(line)
                        if "message" in data and "content" in data["message"]:
                            token = data["message"]["content"]
                            if token:
                                yield token
                        if data.get("done", False):
                            break
                    except json.JSONDecodeError:
                        continue
    except Exception as e:
        logger.error(f"Streaming error: {str(e)}")
        yield f"Error: {str(e)}"
