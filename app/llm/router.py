import time
import logging

logger = logging.getLogger(__name__)

CODING_PATTERNS = [
    "fix", "debug", "code", "function", "class", "method", "error",
    "bug", "script", "implement", "refactor", "syntax",
    "python", "javascript", "typescript", "api", "algorithm",
    "explain how", "how does", "how is", "what does", "loop", "variable"
]

CODING_THRESHOLD = 2  # at least 2 pattern matches = coding intent
BROWSER_PATTERNS = [
    "browser", "open ", "website", "url", "navigate", "click", "fill", "screenshot"
]

def classify_intent(message: str) -> str:
    """Classify user intent as 'coding' or 'general'."""
    message_lower = message.lower()
    
    coding_score = sum(
        1 for pattern in CODING_PATTERNS 
        if pattern in message_lower
    )
    
    if coding_score >= CODING_THRESHOLD:
        return "coding"
    
    return "general"

def route_model(message: str, default_model: str, coding_model: str) -> str:
    """Route to appropriate model based on intent."""
    message_lower = message.lower()
    if any(pattern in message_lower for pattern in BROWSER_PATTERNS):
        logger.info(f"Intent: browser/general -> Model: {default_model}")
        return default_model

    intent = classify_intent(message)
    
    model_map = {
        "coding": coding_model,
        "general": default_model
    }
    
    chosen = model_map[intent]
    
    # Log the decision
    logger.info(f"Intent: {intent} → Model: {chosen}")
    
    return chosen
