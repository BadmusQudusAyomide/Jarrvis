from pydantic import BaseModel
from typing import Dict, Any, Literal
from abc import ABC, abstractmethod

class Action(ABC):
    """Base class for all actions."""
    
    @abstractmethod
    def to_dict(self) -> Dict[str, Any]:
        """Convert action to dictionary for JSON serialization."""
        pass

class ToolCall(Action):
    """Represents a tool call action."""
    
    def __init__(self, tool: str, args: Dict[str, Any] = None):
        self.tool = tool
        self.args = args or {}
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "tool_call",
            "tool": self.tool,
            "args": self.args
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ToolCall":
        return cls(tool=data.get("tool"), args=data.get("args", {}))

class Response(Action):
    """Represents a response action."""
    
    def __init__(self, message: Any, state: str = "thinking"):
        self.message = message
        self.state = state if isinstance(state, str) else str(state)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "response",
            "message": self.message,
            "state": self.state
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Response":
        return cls(message=data.get("message", ""), state=data.get("state", "thinking"))
    
    def is_done(self) -> bool:
        """Check if this response indicates task completion."""
        if self.state == "done":
            return True
        message_text = self.message if isinstance(self.message, str) else str(self.message)
        return "task complete" in message_text.lower()

class ActionFactory:
    """Factory for creating action objects from dictionaries."""
    
    @staticmethod
    def from_dict(data: Dict[str, Any]) -> Action:
        """Create an action object from a dictionary."""
        reserved_states = {"response", "thinking", "done", "tool_call"}

        # Shape: {"tool": "browser_open", "args": {...}}
        if "tool" in data and isinstance(data.get("tool"), str):
            tool_name = data["tool"]
            if tool_name in {"thinking", "done", "response"}:
                return Response(message=data.get("message", ""), state="thinking" if tool_name == "response" else tool_name)
            return ToolCall.from_dict({"tool": tool_name, "args": data.get("args", {})})

        action_type = data.get("type")
        
        if action_type == "tool_call":
            return ToolCall.from_dict(data)
        elif action_type == "response":
            # Some models wrap tool calls inside a response payload.
            msg = data.get("message")
            if isinstance(msg, dict):
                nested = ActionFactory.from_dict(msg)
                if isinstance(nested, ToolCall):
                    return nested
            return Response.from_dict(data)
        elif action_type in {"thinking", "done"}:
            # Some models emit state directly as type.
            return Response(message=data.get("message", ""), state=action_type)
        elif isinstance(action_type, str) and action_type not in reserved_states and "args" in data and "message" not in data:
            # Shape: {"type": "browser_open", "args": {...}}
            return ToolCall.from_dict({"tool": action_type, "args": data.get("args", {})})
        elif "message" in data:
            # Fallback for loosely structured response objects.
            return Response(message=data.get("message", ""), state=data.get("state", "thinking"))
        else:
            # Fallback for unknown types
            return Response(message=str(data), state="thinking")
