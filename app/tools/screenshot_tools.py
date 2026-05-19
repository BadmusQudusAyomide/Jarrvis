"""Screenshot tools using PIL.ImageGrab."""
import logging
import os
from datetime import datetime
from PIL import ImageGrab
from app.tools.base import BaseTool, ToolSchema, ToolParameter

logger = logging.getLogger(__name__)


class ScreenshotTool(BaseTool):
    """Capture a screenshot of the desktop and save to workspace."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="screenshot",
            description="Capture a screenshot of the entire desktop and save to workspace.",
            parameters=[
                ToolParameter(
                    name="filename",
                    type="string",
                    description="Optional filename (without extension). Defaults to timestamp.",
                    required=False
                ),
                ToolParameter(
                    name="save_to_workspace",
                    type="boolean",
                    description="Save to workspace directory (default: true)",
                    required=False
                )
            ],
            return_type="string"
        )

    def execute(self, filename: str = None, save_to_workspace: bool = True, **kwargs) -> str:
        try:
            # Capture the screenshot
            screenshot = ImageGrab.grab()
            
            # Generate filename if not provided
            if not filename:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"screenshot_{timestamp}"
            
            # Ensure filename has .png extension
            if not filename.lower().endswith('.png'):
                filename += '.png'
            
            # Determine save path
            if save_to_workspace:
                workspace_path = os.path.join(os.getcwd(), 'workspace')
                os.makedirs(workspace_path, exist_ok=True)
                filepath = os.path.join(workspace_path, filename)
            else:
                filepath = filename
            
            # Save the screenshot
            screenshot.save(filepath, 'PNG')
            screenshot.close()
            
            logger.info(f"Screenshot saved to {filepath}")
            return f"Screenshot saved to: {filepath}"
            
        except Exception as e:
            logger.error(f"Failed to capture screenshot: {str(e)}", exc_info=True)
            return f"Error capturing screenshot: {str(e)}"
