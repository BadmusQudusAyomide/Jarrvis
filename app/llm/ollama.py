"""Groq chat client. Historically wrapped a local Ollama server too — that's
gone now, this module only talks to Groq's OpenAI-compatible API."""
import requests
import time
import logging
import os
from dotenv import load_dotenv
from app.config import DEFAULT_MODEL, SYSTEM_PROMPT

load_dotenv()

logger = logging.getLogger(__name__)

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.getenv("GROQ_MODEL", DEFAULT_MODEL).strip()
GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
GROQ_TIMEOUT = int(os.getenv("GROQ_TIMEOUT", "60"))

# Second Groq account for coding tasks — falls back to primary key if not set
GROQ_API_KEY_CODING = os.getenv("GROQ_API_KEY_CODING", "").strip() or GROQ_API_KEY
GROQ_MODEL_CODING = os.getenv("GROQ_MODEL_CODING", "qwen-qwq-32b").strip()


def _post_groq(messages: list, api_key: str, model: str, tools: list = None, tool_choice: str = None) -> requests.Response:
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"model": model, "messages": messages, "stream": False}
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = tool_choice or "auto"
    return requests.post(f"{GROQ_BASE_URL}/chat/completions", json=payload, headers=headers, timeout=GROQ_TIMEOUT)


def _chat_with_groq_raw(messages: list, api_key: str = None, model: str = None, tools: list = None) -> dict:
    """Chat request against Groq. Returns the raw `message` object from the API
    (has `content` and, if tools were passed and used, `tool_calls`).

    On 429 (rate limit): waits the Retry-After seconds (capped at 30s) then
    retries once on the same account, then tries the other account as fallback.
    """
    key = api_key or GROQ_API_KEY
    chosen_model = model or GROQ_MODEL

    if not key:
        return {"content": "Error: GROQ_API_KEY is not set"}

    def _extract(res: requests.Response) -> dict:
        return res.json().get("choices", [{}])[0].get("message", {"content": ""})

    try:
        res = _post_groq(messages, key, chosen_model, tools)

        if res.status_code == 200:
            return _extract(res)

        if res.status_code == 429:
            retry_after = int(res.headers.get("Retry-After", 5))
            wait = min(retry_after, 30)
            logger.warning(f"Groq 429 rate limit — waiting {wait}s then retrying...")
            time.sleep(wait)
            res = _post_groq(messages, key, chosen_model, tools)
            if res.status_code == 200:
                return _extract(res)

            other_key = GROQ_API_KEY_CODING if key == GROQ_API_KEY else GROQ_API_KEY
            other_model = GROQ_MODEL_CODING if key == GROQ_API_KEY else GROQ_MODEL
            if other_key and other_key != key:
                logger.warning("Still rate-limited — switching to other Groq account...")
                res = _post_groq(messages, other_key, other_model, tools)
                if res.status_code == 200:
                    return _extract(res)

            return {"content": "I'm getting too many requests right now — please try again in a moment."}

        return {"content": f"Error talking to Groq: HTTP {res.status_code}"}

    except Exception as e:
        return {"content": f"Error talking to Groq: {str(e)}"}


def _chat_with_groq(messages: list, api_key: str = None, model: str = None) -> str:
    """Chat request against Groq, returning plain text content."""
    return _chat_with_groq_raw(messages, api_key, model).get("content") or ""


def _build_messages(system_prompt: str, history: list) -> list:
    """Build the messages list with system prompt prepended."""
    return [{"role": "system", "content": system_prompt}] + history


def chat_with_ollama(history: list, model: str = None, system_prompt: str = None):
    """Send conversation history + system prompt to Groq."""
    model_to_use = model or GROQ_MODEL
    prompt_to_use = system_prompt or SYSTEM_PROMPT
    messages = _build_messages(prompt_to_use, history)

    from app.config import CODING_MODEL
    if model_to_use == CODING_MODEL and GROQ_API_KEY_CODING:
        return _chat_with_groq(messages, api_key=GROQ_API_KEY_CODING, model=GROQ_MODEL_CODING)
    return _chat_with_groq(messages, model=model_to_use)


def chat_with_ollama_single(message: str, history: list = None, model: str = None):
    """Send a single message to the model with optional history (no system prompt)."""
    model_to_use = model or GROQ_MODEL
    messages = list(history) if history else []
    messages.append({"role": "user", "content": message})

    from app.config import CODING_MODEL
    if model_to_use == CODING_MODEL and GROQ_API_KEY_CODING:
        return _chat_with_groq(messages, api_key=GROQ_API_KEY_CODING, model=GROQ_MODEL_CODING)
    return _chat_with_groq(messages, model=model_to_use)


def chat_with_tools(history: list, tools: list, model: str = None, system_prompt: str = None) -> dict:
    """Chat using Groq's native function-calling API.

    Returns the raw assistant message dict: {"content": ..., "tool_calls": [...]}
    where each tool_call is {"id", "type": "function", "function": {"name", "arguments"}}.
    """
    model_to_use = model or GROQ_MODEL
    prompt_to_use = system_prompt or SYSTEM_PROMPT
    messages = _build_messages(prompt_to_use, history)

    from app.config import CODING_MODEL
    if model_to_use == CODING_MODEL and GROQ_API_KEY_CODING:
        return _chat_with_groq_raw(messages, api_key=GROQ_API_KEY_CODING, model=GROQ_MODEL_CODING, tools=tools)
    return _chat_with_groq_raw(messages, model=model_to_use, tools=tools)
