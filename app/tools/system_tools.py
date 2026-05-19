import datetime
import platform
import psutil
import logging
from app.tools.base import BaseTool, ToolSchema, ToolParameter
from app.tools.web_tools import WebSearchTool, WebFetchTool
from app.tools.file_tools import ReadFileTool, WriteFileTool, EditFileTool, ListDirectoryTool, SearchFilesTool, DeleteFileTool, MoveRenameTool
from app.tools.math_tools import CalculatorTool, UnitConversionTool
from app.tools.process_tools import ListProcessesTool, KillProcessTool, LaunchAppTool, IsProcessRunningTool
from app.tools.terminal_tools import ExecuteCommandTool
from app.tools.browser_tools import (BrowserOpenTool, BrowserGetTextTool, BrowserScreenshotTool, 
                                      BrowserClickTool, BrowserFillTool, BrowserCloseTool, 
                                      BrowserScrollTool, BrowserExecuteJSTool, BrowserGetHTMLTool)
from app.tools.notification_tools import SendNotificationTool
from app.tools.clipboard_tools import ReadClipboardTool, WriteClipboardTool
from app.tools.screenshot_tools import ScreenshotTool
from app.tools.calendar_tools import GetCalendarEventsTool, CreateCalendarEventTool, GetTodaysEventsTool
from app.tools.gmail_tools import GetEmailsTool, ReadEmailTool, SendEmailTool, MarkEmailAsReadTool, GetUnreadEmailsTool
from app.tools.code_tools import ExecuteCodeTool
from app.tools.codebase_tools import IndexCodebaseTool, SearchCodebaseTool, GetFileSummaryTool
from app.tools.git_tools import (
    GitStatusTool, GitLogTool, GitDiffTool,
    GitAddTool, GitCommitTool, GitPushTool, GitPullTool,
    GitCheckoutTool, GitCreateBranchTool
)
from app.tools.twitter_tools import (
    PostTweetTool, GetHomeTimelineTool, SearchTweetsTool,
    GetUserTweetsTool, DeleteTweetTool
)
from app.tools.media_tools import DownloadMediaTool

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class GetTimeTool(BaseTool):
    """Tool to get the current time."""
    
    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="get_time",
            description="Returns the current time in YYYY-MM-DD HH:MM:SS format",
            parameters=[],
            return_type="string"
        )
    
    def execute(self, **kwargs) -> str:
        try:
            return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        except Exception as e:
            logger.error(f"GetTimeTool failed: {str(e)}")
            raise

class GetSystemInfoTool(BaseTool):
    """Tool to get system information."""
    
    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="get_system_info",
            description="Returns system information including platform, CPU usage, RAM usage, and RAM details",
            parameters=[],
            return_type="dict"
        )
    
    def execute(self, **kwargs) -> dict:
        try:
            cpu_percent = psutil.cpu_percent(interval=1)
            ram = psutil.virtual_memory()
            
            return {
                "platform": platform.system(),
                "cpu_usage": f"{cpu_percent}%",
                "ram_usage": f"{ram.percent}%",
                "ram_available": f"{ram.available / (1024**3):.2f} GB",
                "ram_total": f"{ram.total / (1024**3):.2f} GB"
            }
        except Exception as e:
            logger.error(f"GetSystemInfoTool failed: {str(e)}")
            raise

# Tool registry - maps tool names to tool instances
TOOLS = {
    "get_time": GetTimeTool(),
    "get_system_info": GetSystemInfoTool(),
    "web_search": WebSearchTool(),
    "web_fetch": WebFetchTool(),
    "read_file": ReadFileTool(),
    "write_file": WriteFileTool(),
    "edit_file": EditFileTool(),
    "list_directory": ListDirectoryTool(),
    "search_files": SearchFilesTool(),
    "delete_file": DeleteFileTool(),
    "move_rename": MoveRenameTool(),
    "calculate": CalculatorTool(),
    "convert_units": UnitConversionTool(),
    "list_processes": ListProcessesTool(),
    "kill_process": KillProcessTool(),
    "launch_app": LaunchAppTool(),
    "is_process_running": IsProcessRunningTool(),
    "execute_command": ExecuteCommandTool(),
    "browser_open": BrowserOpenTool(),
    "browser_get_text": BrowserGetTextTool(),
    "browser_screenshot": BrowserScreenshotTool(),
    "browser_click": BrowserClickTool(),
    "browser_fill": BrowserFillTool(),
    "browser_close": BrowserCloseTool(),
    "browser_scroll": BrowserScrollTool(),
    "browser_execute_js": BrowserExecuteJSTool(),
    "browser_get_html": BrowserGetHTMLTool(),
    "send_notification": SendNotificationTool(),
    "read_clipboard": ReadClipboardTool(),
    "write_clipboard": WriteClipboardTool(),
    "screenshot": ScreenshotTool(),
    "get_calendar_events": GetCalendarEventsTool(),
    "create_calendar_event": CreateCalendarEventTool(),
    "get_todays_events": GetTodaysEventsTool(),
    "get_emails": GetEmailsTool(),
    "read_email": ReadEmailTool(),
    "send_email": SendEmailTool(),
    "mark_email_as_read": MarkEmailAsReadTool(),
    "get_unread_emails": GetUnreadEmailsTool(),
    "execute_code": ExecuteCodeTool(),
    "index_codebase": IndexCodebaseTool(),
    "search_codebase": SearchCodebaseTool(),
    "get_file_summary": GetFileSummaryTool(),
    "git_status": GitStatusTool(),
    "git_log": GitLogTool(),
    "git_diff": GitDiffTool(),
    "git_add": GitAddTool(),
    "git_commit": GitCommitTool(),
    "git_push": GitPushTool(),
    "git_pull": GitPullTool(),
    "git_checkout": GitCheckoutTool(),
    "git_create_branch": GitCreateBranchTool(),
    "post_tweet": PostTweetTool(),
    "get_home_timeline": GetHomeTimelineTool(),
    "search_tweets": SearchTweetsTool(),
    "get_user_tweets": GetUserTweetsTool(),
    "delete_tweet": DeleteTweetTool(),
    "download_media": DownloadMediaTool()
}

def get_tool_descriptions(tool_names: list[str] = None) -> str:
    """Generate tool descriptions from schemas for the system prompt."""
    descriptions = []
    selected = TOOLS
    if tool_names:
        selected = {name: TOOLS[name] for name in tool_names if name in TOOLS}

    for tool_name, tool in selected.items():
        schema = tool.schema
        param_desc = ""
        if schema.parameters:
            params = ", ".join([f"{p.name} ({p.type})" for p in schema.parameters])
            param_desc = f" Parameters: {params}"
        descriptions.append(f"- {schema.name}: {schema.description}. Returns: {schema.return_type}.{param_desc}")
    return "\n".join(descriptions)

def execute_tool(tool_name: str, args: dict = None):
    """Execute a tool by name with optional arguments with enhanced error handling."""
    if tool_name not in TOOLS:
        logger.error(f"Tool not found: {tool_name}")
        return f"Error: Tool '{tool_name}' not found"
    
    tool = TOOLS[tool_name]
    args = args or {}
    
    # Validate arguments
    if not tool.validate_args(args):
        logger.error(f"Invalid arguments for tool {tool_name}: {args}")
        return f"Error: Invalid arguments for tool '{tool_name}'"
    
    try:
        result = tool.execute(**args)
        if isinstance(result, str) and result.lower().startswith("error"):
            logger.warning(f"Tool {tool_name} returned error result: {result}")
        else:
            logger.info(f"Tool {tool_name} executed successfully")
        return result
    except Exception as e:
        logger.error(f"Error executing tool {tool_name}: {str(e)}", exc_info=True)
        return f"Error executing tool '{tool_name}': {str(e)}"
