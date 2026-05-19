from typing import List, Dict, Any
import logging
from app.llm.ollama import chat_with_ollama
from app.config import DEFAULT_MODEL

logger = logging.getLogger(__name__)

# Context window limits (conservative for 8k context models)
MAX_MESSAGES = 20  # Max conversation turns before summarization
MAX_TURNS_TO_KEEP = 6  # Keep last N turns unsummarized for continuity
SUMMARY_TRIGGER_THRESHOLD = 15  # Start summarizing after this many messages

class ContextManager:
    """Manages conversation context by summarizing old messages."""
    
    def __init__(self, max_messages: int = MAX_MESSAGES, keep_recent: int = MAX_TURNS_TO_KEEP):
        self.max_messages = max_messages
        self.keep_recent = keep_recent
        self.summary = None  # Running summary of old conversation
        
    def should_summarize(self, history: List[Dict[str, Any]]) -> bool:
        """Check if conversation history is getting too long."""
        return len(history) > SUMMARY_TRIGGER_THRESHOLD
    
    def create_summary(self, messages: List[Dict[str, Any]]) -> str:
        """Create a summary of conversation messages using LLM."""
        if not messages:
            return ""
        
        # Format messages for summarization
        conversation_text = "\n".join([
            f"{msg['role']}: {msg['content']}" 
            for msg in messages
        ])
        
        prompt = f"""Summarize the following conversation concisely. Extract key facts, decisions, and context that would be important to remember for future interactions. Be brief but comprehensive.

Conversation:
{conversation_text}

Summary:"""
        
        try:
            summary = chat_with_ollama(
                history=[],
                model=DEFAULT_MODEL,
                system_prompt=prompt
            )
            logger.info(f"Created summary: {summary[:100]}...")
            return summary.strip()
        except Exception as e:
            logger.error(f"Failed to create summary: {str(e)}")
            # Fallback: simple concatenation of key points
            return self._simple_fallback_summary(messages)
    
    def _simple_fallback_summary(self, messages: List[Dict[str, Any]]) -> str:
        """Create a simple summary when LLM fails."""
        key_points = []
        for msg in messages:
            if msg['role'] == 'user' and len(msg['content']) < 200:
                key_points.append(f"User said: {msg['content'][:100]}")
        return " | ".join(key_points[:5])  # Keep only first 5 points
    
    def compress_history(self, history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Compress history by summarizing old messages."""
        if not self.should_summarize(history):
            return history
        
        logger.info(f"Compressing history: {len(history)} messages")
        
        # Split into: messages to summarize vs recent messages to keep
        cutoff = len(history) - (self.keep_recent * 2)  # Each turn = 2 messages
        
        if cutoff <= 0:
            return history
        
        messages_to_summarize = history[:cutoff]
        recent_messages = history[cutoff:]
        
        # Create or update summary
        new_summary = self.create_summary(messages_to_summarize)
        
        if self.summary:
            # Merge with existing summary
            self.summary = f"{self.summary}\n\nAdditional context: {new_summary}"
        else:
            self.summary = new_summary
        
        # Build compressed history
        compressed = []
        
        # Add summary as system context if we have one
        if self.summary:
            compressed.append({
                "role": "system",
                "content": f"Previous conversation summary: {self.summary}"
            })
        
        # Add recent messages
        compressed.extend(recent_messages)
        
        logger.info(f"History compressed from {len(history)} to {len(compressed)} messages")
        return compressed
    
    def get_current_summary(self) -> str:
        """Get the current conversation summary."""
        return self.summary or ""
    
    def reset(self):
        """Reset the context manager (e.g., for new conversations)."""
        self.summary = None
        logger.info("Context manager reset")


def manage_context(history: List[Dict[str, Any]], session_id: str = "local") -> List[Dict[str, Any]]:
    """Global function to manage context for a session."""
    # In production, you'd store context managers per session
    # For now, create a new one each time (stateless approach)
    manager = ContextManager()
    return manager.compress_history(history)
