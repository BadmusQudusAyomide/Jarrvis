conversations = {}  # { session_id: [messages] }

MAX_HISTORY = 10

def get_history(session_id: str):
    return conversations.get(session_id, [])

def add_message(session_id: str, role: str, content: str):
    if session_id not in conversations:
        conversations[session_id] = []
    
    conversations[session_id].append({
        "role": role,
        "content": content
    })
    
    # Trim to last MAX_HISTORY messages
    conversations[session_id] = conversations[session_id][-MAX_HISTORY:]

def clear_history(session_id: str):
    conversations[session_id] = []
