import requests
import time
import logging
import os
from dotenv import load_dotenv
from app.config import OLLAMA_URL, DEFAULT_MODEL, SYSTEM_PROMPT

load_dotenv()  # ensure .env is loaded before reading OLLAMA_TIMEOUT

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds
TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "60"))  # seconds — override with OLLAMA_TIMEOUT in .env

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant").strip()
GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
GROQ_TIMEOUT = int(os.getenv("GROQ_TIMEOUT", "60"))

# Second Groq account for coding tasks — falls back to primary key if not set
GROQ_API_KEY_CODING = os.getenv("GROQ_API_KEY_CODING", "").strip() or GROQ_API_KEY
GROQ_MODEL_CODING = os.getenv("GROQ_MODEL_CODING", "qwen-qwq-32b").strip()


def _chat_with_groq(messages: list, api_key: str = None, model: str = None) -> str:
    """Chat request against Groq OpenAI-compatible API.
    Pass api_key/model explicitly to use a different account or model.
    """
    key = api_key or GROQ_API_KEY
    chosen_model = model or GROQ_MODEL

    if not key:
        return "Error: GROQ_API_KEY is not set"

    url = f"{GROQ_BASE_URL}/chat/completions"
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    payload = {"model": chosen_model, "messages": messages, "stream": False}

    try:
        res = requests.post(url, json=payload, headers=headers, timeout=GROQ_TIMEOUT)
        if res.status_code != 200:
            return f"Error talking to Groq: HTTP {res.status_code}"
        return (
            res.json().get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
        )
    except Exception as e:
        return f"Error talking to Groq: {str(e)}"

def _build_messages(system_prompt: str, history: list) -> list:
    """Build the messages list with system prompt prepended."""
    return [{"role": "system", "content": system_prompt}] + history


def _ollama_model_ready(model: str) -> bool:
    """Check if Ollama is up AND the specific model is installed.
    Returns False immediately if the server is unreachable or the model isn't in the list.
    This avoids 60s timeouts when the model isn't loaded.
    """
    try:
        resp = requests.get(f"{OLLAMA_URL}/api/tags", timeout=2)
        if resp.status_code != 200:
            return False
        models = [m.get("name", "") for m in resp.json().get("models", [])]
        # Match by prefix so "llama3.2:3b" matches "llama3.2:3b" etc.
        return any(model.split(":")[0] in m for m in models)
    except Exception:
        return False


def chat_with_ollama(history: list, model: str = None, system_prompt: str = None):
    """Send conversation history to specified model with system prompt with retry logic."""
    url = f"{OLLAMA_URL}/api/chat"

    # Use provided model or default
    model_to_use = model or DEFAULT_MODEL
    # Use provided system prompt or default
    prompt_to_use = system_prompt or SYSTEM_PROMPT

    # Skip Ollama if the model isn't installed — avoids 60s timeout per request
    if not _ollama_model_ready(model_to_use):
        logger.warning(f"Ollama model '{model_to_use}' not ready. Going straight to Groq.")
        from app.config import CODING_MODEL
        if model_to_use == CODING_MODEL and GROQ_API_KEY_CODING:
            return _chat_with_groq(_build_messages(prompt_to_use, history), api_key=GROQ_API_KEY_CODING, model=GROQ_MODEL_CODING)
        if GROQ_API_KEY:
            return _chat_with_groq(_build_messages(prompt_to_use, history))
        return "Error: Ollama model not available and no Groq API key is set."

    # Prepend system prompt to conversation
    messages = [
        {
            "role": "system",
            "content": prompt_to_use
        }
    ]
    
    # Add conversation history
    messages.extend(history)

    payload = {
        "model": model_to_use,
        "messages": messages,
        "stream": False,
        # Keep model in memory for faster subsequent requests.
        "keep_alive": "5m"
    }

    # Retry logic
    for attempt in range(MAX_RETRIES):
        try:
            res = requests.post(url, json=payload, timeout=TIMEOUT)
            
            if res.status_code == 200:
                return res.json().get("message", {}).get("content", "")
            else:
                if attempt < MAX_RETRIES - 1:
                    logger.warning(f"Attempt {attempt + 1} failed with status {res.status_code}, retrying...")
                    time.sleep(RETRY_DELAY)
                    continue
                return f"Error talking to model: HTTP {res.status_code}"
        
        except requests.exceptions.Timeout:
            # Timeout usually means model is slow/warming up; retries often repeat the same long wait.
            logger.warning(f"Attempt {attempt + 1} timed out after {TIMEOUT}s")
            break
        
        except requests.exceptions.ConnectionError:
            if attempt < MAX_RETRIES - 1:
                logger.warning(f"Attempt {attempt + 1} connection failed, retrying...")
                time.sleep(RETRY_DELAY)
                continue
            return "Error: Could not connect to Ollama server"
        
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                logger.warning(f"Attempt {attempt + 1} failed with {str(e)}, retrying...")
                time.sleep(RETRY_DELAY)
                continue
            return f"Error talking to model: {str(e)}"
    
    # Optional fallback model for resilience when the selected model is too slow/unavailable.
    fallback_model = os.getenv("FAST_MODEL_FALLBACK", "").strip()
    if fallback_model and fallback_model != model_to_use:
        logger.warning(f"Trying fallback model due to failure: {fallback_model}")
        fallback_payload = {
            "model": fallback_model,
            "messages": messages,
            "stream": False,
            "keep_alive": "5m"
        }
        try:
            res = requests.post(url, json=fallback_payload, timeout=TIMEOUT)
            if res.status_code == 200:
                return res.json().get("message", {}).get("content", "")
        except Exception:
            pass

    if GROQ_API_KEY or GROQ_API_KEY_CODING:
        logger.warning("Ollama unavailable/slow. Falling back to Groq.")
        # Use coding account+model if the requested model is the coding model
        from app.config import CODING_MODEL
        if model_to_use == CODING_MODEL and GROQ_API_KEY_CODING:
            groq_resp = _chat_with_groq(messages, api_key=GROQ_API_KEY_CODING, model=GROQ_MODEL_CODING)
        else:
            groq_resp = _chat_with_groq(messages)
        if not groq_resp.startswith("Error:"):
            return groq_resp

    return "Error: Model request timed out"

def chat_with_ollama_single(message: str, history: list = None, model: str = None):
    """Send a single message to the model with optional history (no system prompt) with retry logic."""
    url = f"{OLLAMA_URL}/api/chat"
    
    # Use provided model or default
    model_to_use = model or DEFAULT_MODEL

    messages = []
    
    # Add history if provided
    if history:
        messages.extend(history)
    
    # Add the new message
    messages.append({
        "role": "user",
        "content": message
    })

    payload = {
        "model": model_to_use,
        "messages": messages,
        "stream": False,
        "keep_alive": "5m"
    }

    # Retry logic
    for attempt in range(MAX_RETRIES):
        try:
            res = requests.post(url, json=payload, timeout=TIMEOUT)
            
            if res.status_code == 200:
                return res.json().get("message", {}).get("content", "")
            else:
                if attempt < MAX_RETRIES - 1:
                    logger.warning(f"Attempt {attempt + 1} failed with status {res.status_code}, retrying...")
                    time.sleep(RETRY_DELAY)
                    continue
                return f"Error talking to model: HTTP {res.status_code}"
        
        except requests.exceptions.Timeout:
            logger.warning(f"Attempt {attempt + 1} timed out after {TIMEOUT}s")
            break
        
        except requests.exceptions.ConnectionError:
            if attempt < MAX_RETRIES - 1:
                logger.warning(f"Attempt {attempt + 1} connection failed, retrying...")
                time.sleep(RETRY_DELAY)
                continue
            return "Error: Could not connect to Ollama server"
        
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                logger.warning(f"Attempt {attempt + 1} failed with {str(e)}, retrying...")
                time.sleep(RETRY_DELAY)
                continue
            return f"Error talking to model: {str(e)}"
    
    if GROQ_API_KEY or GROQ_API_KEY_CODING:
        logger.warning("Ollama unavailable/slow (single). Falling back to Groq.")
        from app.config import CODING_MODEL
        if model_to_use == CODING_MODEL and GROQ_API_KEY_CODING:
            groq_resp = _chat_with_groq(messages, api_key=GROQ_API_KEY_CODING, model=GROQ_MODEL_CODING)
        else:
            groq_resp = _chat_with_groq(messages)
        if not groq_resp.startswith("Error:"):
            return groq_resp

    return "Error: Model request timed out"
