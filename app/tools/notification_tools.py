"""Desktop notification tools using plyer."""
import logging
from plyer import notification
from app.tools.base import BaseTool, ToolSchema, ToolParameter

logger = logging.getLogger(__name__)


class SendNotificationTool(BaseTool):
    """Send a desktop notification."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="send_notification",
            description="Send a desktop notification (Windows toast).",
            parameters=[
                ToolParameter(
                    name="title",
                    type="string",
                    description="Notification title",
                    required=True
                ),
                ToolParameter(
                    name="message",
                    type="string",
                    description="Notification body text",
                    required=True
                ),
                ToolParameter(
                    name="duration",
                    type="integer",
                    description="How long the notification shows in seconds (default: 5)",
                    required=False
                ),
                ToolParameter(
                    name="app_icon",
                    type="string",
                    description="Optional path to a .ico icon file",
                    required=False
                )
            ],
            return_type="string"
        )

    def execute(self, title: str, message: str, duration: int = 5, app_icon: str = None, **kwargs) -> str:
        try:
            duration = max(1, int(duration))
            notification.notify(
                title=title,
                message=message,
                timeout=duration,
                app_icon=app_icon
            )
            logger.info("Notification sent")
            return f"Notification sent: {title}"
        except Exception as e:
            logger.error(f"Failed to send notification: {str(e)}", exc_info=True)
            return f"Error sending notification: {str(e)}"

