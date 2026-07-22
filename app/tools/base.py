from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, Type
from abc import ABC, abstractmethod

class ToolParameter(BaseModel):
    """Schema for a tool parameter."""
    name: str
    type: str
    description: str
    required: bool = True
    items_type: Optional[str] = None
    """For type='list'/'array' params: the JSON schema type of each item (e.g. 'integer')."""

class ToolSchema(BaseModel):
    """Structured schema for a tool."""
    name: str
    description: str
    parameters: list[ToolParameter] = []
    return_type: str = "string"

class BaseTool(ABC):
    """Base class for all tools with structured schema."""
    
    @property
    @abstractmethod
    def schema(self) -> ToolSchema:
        """Return the tool's schema."""
        pass
    
    @abstractmethod
    def execute(self, **kwargs) -> Any:
        """Execute the tool with given arguments."""
        pass
    
    def validate_args(self, args: Dict[str, Any]) -> bool:
        """Validate arguments against schema."""
        schema = self.schema
        for param in schema.parameters:
            if param.required and param.name not in args:
                return False
        return True
