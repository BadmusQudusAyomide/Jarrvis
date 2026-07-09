"""Streaming support for Groq chat responses."""
import requests
import json
import logging
from app.config import SYSTEM_PROMPT
from app.llm.ollama import GROQ_API_KEY, GROQ_MODEL, GROQ_BASE_URL

logger = logging.getLogger(__name__)
TIMEOUT = 300  # seconds for streaming


def chat_with_ollama_stream(history: list, model: str = None, system_prompt: str = None):
    """Stream conversation history to Groq, yielding tokens as they arrive."""
    model_to_use = model or GROQ_MODEL
    prompt_to_use = system_prompt or SYSTEM_PROMPT

    if not GROQ_API_KEY:
        yield "Error: GROQ_API_KEY is not set"
        return

    messages = [{"role": "system", "content": prompt_to_use}]
    messages.extend(history)

    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": model_to_use, "messages": messages, "stream": True}

    try:
        with requests.post(f"{GROQ_BASE_URL}/chat/completions", json=payload, headers=headers,
                            stream=True, timeout=TIMEOUT) as res:
            if res.status_code != 200:
                yield f"Error: HTTP {res.status_code}"
                return

            for line in res.iter_lines():
                if not line:
                    continue
                decoded = line.decode("utf-8") if isinstance(line, bytes) else line
                if not decoded.startswith("data: "):
                    continue
                data_str = decoded[len("data: "):]
                if data_str.strip() == "[DONE]":
                    break
                try:
                    data = json.loads(data_str)
                    delta = data.get("choices", [{}])[0].get("delta", {})
                    token = delta.get("content")
                    if token:
                        yield token
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        logger.error(f"Streaming error: {str(e)}")
        yield f"Error: {str(e)}"
