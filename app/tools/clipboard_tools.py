"""Clipboard tools using pyperclip."""
import logging
import pyperclip
from app.tools.base import BaseTool, ToolSchema, ToolParameter

logger = logging.getLogger(__name__)


class ReadClipboardTool(BaseTool):
    """Read text from the Windows clipboard."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="read_clipboard",
            description="Read text content from the Windows clipboard.",
            parameters=[],
            return_type="string"
        )

    def execute(self, **kwargs) -> str:
        try:
            content = pyperclip.paste()
            logger.info("Clipboard content read successfully")
            if content:
                return f"Clipboard content: {content}"
            else:
                return "Clipboard is empty or contains non-text content"
        except Exception as e:
            logger.error(f"Failed to read clipboard: {str(e)}", exc_info=True)
            return f"Error reading clipboard: {str(e)}"


class WriteClipboardTool(BaseTool):
    """Write text to the Windows clipboard."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="write_clipboard",
            description="Write text content to the Windows clipboard.",
            parameters=[
                ToolParameter(
                    name="text",
                    type="string",
                    description="Text content to copy to clipboard",
                    required=True
                )
            ],
            return_type="string"
        )

    def execute(self, text: str, **kwargs) -> str:
        try:
            pyperclip.copy(text)
            logger.info("Text copied to clipboard successfully")
            return f"Text copied to clipboard: {len(text)} characters"
        except Exception as e:
            logger.error(f"Failed to write to clipboard: {str(e)}", exc_info=True)
            return f"Error writing to clipboard: {str(e)}"
