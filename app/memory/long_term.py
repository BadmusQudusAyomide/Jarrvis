import chromadb
from datetime import datetime
import os
import re
import logging
from app.llm.ollama import chat_with_ollama
from app.config import DEFAULT_MODEL

logger = logging.getLogger(__name__)

# Initialize ChromaDB with persistent storage
chroma_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "chroma")
client = chromadb.PersistentClient(path=chroma_path)
collection = client.get_or_create_collection("jarvis_memory")

# What patterns are worth remembering (statements/facts only)
MEMORY_TRIGGERS = [
    "my name is", "i am", "i work", "i use", "i prefer",
    "i like", "i hate", "i'm building", "my project",
    "my favorite", "i'm learning", "i live", "i study",
    "remember that", "don't forget", "important to note"
]

# Question patterns to exclude (at start of sentence)
QUESTION_START_PATTERNS = [
    r"^(what|where|when|why|how|who|which|can you|could you|would you|will you|do you|are you|is there|is it)\b",
    r"^(tell me|show me|give me|list)\b"
]

# Patterns that indicate queries/requests, not facts
QUERY_PATTERNS = [
    "check", "monitor", "tell me", "show me", "what is", "how to",
    "can you", "could you", "would you", "help me", "i need"
]

def is_worth_remembering(message: str) -> bool:
    """Check if message contains information worth storing in long-term memory."""
    message_lower = message.lower().strip()
    
    # Exclude questions (check if starts with question word)
    for pattern in QUESTION_START_PATTERNS:
        if re.match(pattern, message_lower):
            return False
    
    # Exclude messages with question marks
    if "?" in message:
        return False
    
    # Exclude query/command patterns
    if any(pattern in message_lower for pattern in QUERY_PATTERNS):
        return False
    
    # Only store if it contains a memory trigger
    return any(trigger in message_lower for trigger in MEMORY_TRIGGERS)

def extract_facts_with_llm(message: str) -> str:
    """Use LLM to extract factual information from a message."""
    prompt = """You are a memory extraction system. Your job is to extract ONLY factual statements about the user from messages.
    
Rules:
- Extract facts about preferences, identity, work, projects, habits
- DO NOT extract questions, requests, commands, or temporary states
- If no facts are found, return "NONE"
- Keep the extracted fact concise and in first-person perspective

Message: "{message}"

Extracted fact:"""
    
    try:
        response = chat_with_ollama(
            history=[],
            model=DEFAULT_MODEL,
            system_prompt=prompt.replace("{message}", message)
        )
        
        fact = response.strip()
        if fact.lower() == "none" or len(fact) < 10:
            return None
        return fact
    except Exception as e:
        logger.error(f"LLM extraction failed: {str(e)}")
        return None

def store_memory(session_id: str, content: str, category: str = "general"):
    """Store a memory in ChromaDB with metadata."""
    # First, try to extract facts using LLM
    extracted_fact = extract_facts_with_llm(content)
    
    # If LLM extracted a fact, use that; otherwise use original if it passes heuristic
    memory_content = extracted_fact if extracted_fact else content
    
    if not memory_content or memory_content.lower() == "none":
        logger.info(f"No facts extracted, skipping storage")
        return
    
    memory_id = f"{session_id}_{datetime.now().timestamp()}"
    collection.add(
        documents=[memory_content],
        metadatas=[{
            "session_id": session_id,
            "category": category,
            "timestamp": datetime.now().isoformat()
        }],
        ids=[memory_id]
    )
    logger.info(f"Stored memory: {memory_content[:50]}...")

def retrieve_memories(query: str, session_id: str, n_results: int = 3) -> list:
    """Retrieve relevant memories based on semantic similarity."""
    try:
        results = collection.query(
            query_texts=[query],
            n_results=n_results,
            where={"session_id": session_id}
        )
        return results["documents"][0] if results["documents"] else []
    except:
        return []

def build_memory_context(memories: list) -> str:
    """Build a formatted context string from retrieved memories."""
    if not memories:
        return ""
    joined = "\n".join(f"- {m}" for m in memories)
    return f"\nRelevant things I remember about you:\n{joined}\n"
