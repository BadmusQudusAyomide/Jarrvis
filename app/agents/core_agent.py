from app.llm.ollama import chat_with_ollama
from app.tools.system_tools import execute_tool, TOOLS
from app.utils.parser import parse_all_model_outputs
from app.agents.actions import ToolCall, Response
from app.config import DEFAULT_MODEL
import logging
import re
import json
import ast
from datetime import datetime

logger = logging.getLogger(__name__)

MAX_STEPS = 8
MAX_TOOL_CALLS = 8

class Agent:
    def __init__(self, model: str = None):
        self.model = model or DEFAULT_MODEL
        self.steps = 0
        self.tool_calls = 0
        self.observations = []

    def _smalltalk_direct_response(self, user_message: str):
        """Return deterministic responses for simple chat to avoid unnecessary tool calls."""
        lower = user_message.strip().lower()
        compact = re.sub(r"[^a-z0-9\s']", " ", lower)
        compact = re.sub(r"\s+", " ", compact).strip()

        if compact in {"hi", "hello", "hey", "yo"}:
            return "Hello! How may I assist you today?"
        if compact in {"how are you", "how are you doing", "how r u", "how you dey"}:
            return "I'm doing well, thank you for asking! How can I help you today?"
        if "who are you" in compact:
            return "I am Jarvis, your personal AI assistant. I can help with coding, tasks, tools, and everyday questions."

        # Date difference: "how many days from X to Y" / "X to Y how many days"
        date_diff = self._try_date_diff(user_message)
        if date_diff:
            return date_diff

        return None

    _MONTHS = {
        "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
        "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6,
        "jul": 7, "july": 7, "aug": 8, "august": 8, "sep": 9, "september": 9,
        "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
    }

    def _try_date_diff(self, text: str):
        """Return day-count answer if message asks how many days between two dates."""
        lower = text.lower()
        if not any(w in lower for w in ["how many day", "days is", "days from", "days between", "days since"]):
            return None

        # Find all date-like tokens: "march 11", "march 11 2026", "11/03", "2026-03-11"
        pattern = (
            r"(\d{1,2})[\/\-](\d{1,2})(?:[\/\-](\d{2,4}))?"   # 11/03 or 11/03/2026
            r"|(\d{4})[\/\-](\d{1,2})[\/\-](\d{1,2})"           # 2026-03-11
            r"|(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
            r"jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
            r"\s+(\d{1,2})(?:\s+(\d{2,4}))?"                     # march 11 2026
            r"|(\d{1,2})\s+(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
            r"jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
            r"(?:\s+(\d{2,4}))?"                                  # 11 march 2026
        )
        dates = []
        now = datetime.now()
        for m in re.finditer(pattern, lower):
            g = m.groups()
            try:
                if g[0]:   # dd/mm or dd/mm/yyyy
                    d, mo = int(g[0]), int(g[1])
                    yr = int(g[2]) if g[2] else now.year
                    yr = yr + 2000 if yr < 100 else yr
                    dates.append(datetime(yr, mo, d))
                elif g[3]: # yyyy-mm-dd
                    dates.append(datetime(int(g[3]), int(g[4]), int(g[5])))
                elif g[6]: # month day [year]
                    mo = self._MONTHS.get(g[6][:3])
                    if mo:
                        d = int(g[7])
                        yr = int(g[8]) if g[8] else now.year
                        yr = yr + 2000 if yr < 100 else yr
                        dates.append(datetime(yr, mo, d))
                elif g[9]: # day month [year]
                    mo = self._MONTHS.get(g[10][:3])
                    if mo:
                        d = int(g[9])
                        yr = int(g[11]) if g[11] else now.year
                        yr = yr + 2000 if yr < 100 else yr
                        dates.append(datetime(yr, mo, d))
            except (ValueError, TypeError):
                continue

        # Replace "today" with today's date
        if "today" in lower:
            dates.append(now.replace(hour=0, minute=0, second=0, microsecond=0))

        if len(dates) >= 2:
            delta = abs((dates[1] - dates[0]).days)
            d1 = dates[0].strftime("%B %d, %Y")
            d2 = dates[1].strftime("%B %d, %Y")
            return f"From {d1} to {d2} is **{delta} days**."

        return None

    def _extract_tool_call_from_text(self, text: str):
        """Best-effort parse of tool call payloads returned as plain text."""
        if not text or not isinstance(text, str):
            return None

        stripped = text.strip()
        candidates = []

        # JSON-like object
        if stripped.startswith("{") and stripped.endswith("}"):
            candidates.append(stripped)

        # fenced block support
        fence_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", stripped, re.DOTALL | re.IGNORECASE)
        if fence_match:
            candidates.append(fence_match.group(1).strip())

        for candidate in candidates:
            parsed = None
            try:
                parsed = json.loads(candidate)
            except Exception:
                try:
                    parsed = ast.literal_eval(candidate)
                except Exception:
                    parsed = None

            if not isinstance(parsed, dict):
                continue

            tool_name = parsed.get("tool") or parsed.get("type")
            args = parsed.get("args", {})

            # Common alternate format: {"post_tweet": "...", "state": "done"}
            if tool_name is None:
                known_tool_keys = [
                    "post_tweet", "get_time", "web_search", "write_file",
                    "read_file", "execute_command", "get_unread_emails"
                ]
                for key in known_tool_keys:
                    if key in parsed:
                        tool_name = key
                        value = parsed.get(key)
                        if isinstance(value, dict):
                            args = value
                        elif key == "post_tweet":
                            args = {"text": value}
                        elif key == "write_file" and isinstance(value, str):
                            args = {"path": "response.txt", "content": value, "append": False}
                        else:
                            args = {}
                        break

            if not tool_name or not isinstance(tool_name, str):
                continue

            # Ignore non-tool "type" values used by the planner protocol.
            if tool_name in {"response", "thinking", "done"}:
                return None

            # Normalize protocol style: {"type":"tool_call","tool":"x","args":{...}}
            if tool_name == "tool_call":
                tool_name = parsed.get("tool")
                args = parsed.get("args", {})

            if not tool_name or not isinstance(args, dict):
                continue

            if tool_name in TOOLS:
                return ToolCall(tool_name, args)

        return None

    def _execute_tool_if_valid(self, tool_name: str, tool_args: dict):
        """Execute only registered tools and return tuple(result, executed)."""
        if tool_name not in TOOLS:
            logger.warning(f"[AGENT] Ignoring unknown tool request: {tool_name}")
            return f"Error: Unknown tool '{tool_name}'", False
        return execute_tool(tool_name, tool_args), True
    
    def think(self, history: list, system_prompt: str) -> list:
        """Have the model think about the current state. Returns list of action objects."""
        try:
            response = chat_with_ollama(history, model=self.model, system_prompt=system_prompt)
            action_list = parse_all_model_outputs(response)
            return action_list
        except Exception as e:
            logger.error(f"Error in think method: {str(e)}", exc_info=True)
            # Return a simple response action as fallback
            return [Response(message=f"I encountered an error: {str(e)}")]

    def _browser_fallback_tool_call(self, user_message: str):
        """Deterministic fallback when model fails to emit tool_call JSON."""
        msg = user_message.strip()
        lower = msg.lower()

        if ("open browser" in lower or "open " in lower) and ("http://" in lower or "https://" in lower):
            m = re.search(r"(https?://\S+)", msg, re.IGNORECASE)
            if m:
                return ToolCall("browser_open", {"url": m.group(1).rstrip(".,")})

        if "screenshot" in lower:
            file_match = re.search(r"(?:as|named)\s+([a-zA-Z0-9_\-\.]+)", msg, re.IGNORECASE)
            filename = file_match.group(1) if file_match else "screenshot.png"
            return ToolCall("browser_screenshot", {"filename": filename})

        if "get the text" in lower or "page text" in lower or "extract text" in lower:
            return ToolCall("browser_get_text", {})

        if "fill" in lower and "search" in lower:
            text_match = re.search(r"['\"](.+?)['\"]", msg)
            text = text_match.group(1) if text_match else ""
            if text:
                # Google-compatible default selector.
                return ToolCall("browser_fill", {"selector": "textarea[name='q']", "text": text})

        if "click" in lower and "search" in lower:
            return ToolCall("browser_click", {"selector": "input[name='btnK']"})

        return None

    def _notification_fallback_tool_call(self, user_message: str):
        """Deterministic fallback for notification requests."""
        msg = user_message.strip()
        lower = msg.lower()

        if "notification" not in lower and "notify" not in lower:
            return None

        # Handle: "Send me a notification saying Jarvis is ready"
        saying_match = re.search(r"(?:saying|that says|with message)\s+(.+)$", msg, re.IGNORECASE)
        body = saying_match.group(1).strip().strip("'\"") if saying_match else "You have a new notification."
        return ToolCall("send_notification", {
            "title": "Jarvis",
            "message": body,
            "duration": 5
        })
    
    def _clipboard_fallback_tool_call(self, user_message: str):
        """Deterministic fallback for clipboard requests."""
        msg = user_message.strip()
        lower = msg.lower()

        # Handle read clipboard requests
        if any(phrase in lower for phrase in ["what's on my clipboard", "whats on my clipboard", "what is on my clipboard", "read clipboard", "clipboard content", "clipboard has"]):
            return ToolCall("read_clipboard", {})
        
        # Handle write clipboard requests
        copy_match = re.search(r"(?:copy|put|add)\s+(?:['\"]?)(.+?)(?:['\"]?)\s+(?:to )?clipboard", msg, re.IGNORECASE)
        if copy_match:
            text_to_copy = copy_match.group(1).strip()
            return ToolCall("write_clipboard", {"text": text_to_copy})
        
        return None
    
    def _screenshot_fallback_tool_call(self, user_message: str):
        """Deterministic fallback for screenshot requests."""
        msg = user_message.strip()
        lower = msg.lower()

        if any(phrase in lower for phrase in ["screenshot", "screen shot", "capture screen", "take screenshot"]):
            # Check for custom filename
            file_match = re.search(r"(?:as|named|save as)\s+([a-zA-Z0-9_\-\.]+)", msg, re.IGNORECASE)
            filename = file_match.group(1) if file_match else None
            return ToolCall("screenshot", {"filename": filename})
        
        return None
    
    def _calendar_fallback_tool_call(self, user_message: str):
        """Deterministic fallback for calendar requests."""
        msg = user_message.strip()
        lower = msg.lower()

        # Handle get today's events
        if any(phrase in lower for phrase in ["what's on my calendar today", "whats on my calendar today", "today's calendar", "calendar today", "my schedule today"]):
            return ToolCall("get_todays_events", {})
        
        # Handle get calendar events
        if any(phrase in lower for phrase in ["calendar events", "upcoming events", "my calendar", "schedule", "what's coming up"]):
            return ToolCall("get_calendar_events", {})
        
        # Handle create calendar event
        create_match = re.search(r"(?:create|add|schedule)\s+(?:a\s+)?(?:calendar\s+)?event\s+(?:called|named)\s+['\"]?([^'\"]+)['\"]?", msg, re.IGNORECASE)
        if create_match:
            title = create_match.group(1).strip()
            return ToolCall("create_calendar_event", {"title": title})
        
        return None
    
    def _gmail_fallback_tool_call(self, user_message: str):
        """Deterministic fallback for Gmail requests."""
        msg = user_message.strip()
        lower = msg.lower()

        # Handle get unread emails
        if any(phrase in lower for phrase in ["unread emails", "new emails", "check my email", "any new email", "unread messages"]):
            return ToolCall("get_unread_emails", {})
        
        # Handle get emails
        if any(phrase in lower for phrase in ["get emails", "check emails", "my emails", "inbox"]):
            return ToolCall("get_emails", {})
        
        # Handle send email
        send_match = re.search(r"(?:send|email)\s+(?:to\s+)?([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})", msg, re.IGNORECASE)
        if send_match:
            to_email = send_match.group(1).strip()
            # Look for subject
            subject_match = re.search(r"(?:subject|about|regarding)\s+['\"]?([^'\"]+)['\"]?", msg, re.IGNORECASE)
            subject = subject_match.group(1).strip() if subject_match else "No subject"
            
            # Look for body/message
            body_match = re.search(r"(?:message|body|saying|say)\s+['\"]?([^'\"]+)['\"]?", msg, re.IGNORECASE)
            body = body_match.group(1).strip() if body_match else "No message content"
            
            return ToolCall("send_email", {"to": to_email, "subject": subject, "body": body})
        
        return None
    
    def _code_fallback_tool_call(self, user_message: str):
        """Deterministic fallback for code execution requests."""
        msg = user_message.strip()
        lower = msg.lower()

        # Handle run/execute code requests
        code_patterns = [
            r"(?:run|execute)\s+(?:this\s+)?(?:python\s+)?code:\s*```(?:python)?\s*\n?([^`]+)```",
            r"(?:run|execute)\s+(?:this\s+)?(?:python\s+)?code:\s*'([^']+)'",
            r"(?:run|execute)\s+(?:this\s+)?(?:python\s+)?code:\s*\"([^\"]+)\"",
        ]
        
        for pattern in code_patterns:
            code_match = re.search(pattern, msg, re.IGNORECASE | re.DOTALL)
            if code_match:
                code = code_match.group(1).strip()
                return ToolCall("execute_code", {"code": code})
        
        # Handle simple "calculate this" or "compute this" requests
        calc_patterns = [
            r"(?:calculate|compute|evaluate)\s+(?:the\s+)?(?:expression\s+)?['\"]?([^'\"]+)['\"]?",
        ]
        
        for pattern in calc_patterns:
            calc_match = re.search(pattern, msg, re.IGNORECASE)
            if calc_match:
                expression = calc_match.group(1).strip()
                # Wrap in a simple Python script
                code = f"""# Calculation
expression = '{expression}'
result = {expression}
print(f"Expression: {{expression}}")
print(f"Result: {{result}}")"""
                return ToolCall("execute_code", {"code": code})
        
        return None
    
    def _codebase_fallback_tool_call(self, user_message: str):
        """Deterministic fallback for codebase indexing and search requests."""
        msg = user_message.strip()
        lower = msg.lower()

        # Handle index codebase requests
        if any(phrase in lower for phrase in ["index my code", "index the codebase", "index project", "scan codebase"]):
            return ToolCall("index_codebase", {})
        
        # Handle search codebase requests
        search_patterns = [
            r"(?:search|find|where is|look for)\s+(?:in\s+)?(?:my\s+)?(?:code|codebase|project)\s+(?:for\s+)?['\"]?([^'\"]+)['\"]?",
            r"(?:where|find)\s+(?:is|are)\s+['\"]?([^'\"]+)['\"]?\s+(?:in\s+)?(?:my\s+)?(?:code|codebase)",
        ]
        
        for pattern in search_patterns:
            search_match = re.search(pattern, msg, re.IGNORECASE)
            if search_match:
                query = search_match.group(1).strip()
                return ToolCall("search_codebase", {"query": query})
        
        # Handle file summary requests - require clean file paths (no spaces before extension)
        summary_patterns = [
            r"(?:summarize|explain|what does)\s+(?:the\s+)?(?:file\s+)?['\"]?([^'\"\s]+\.(?:py|js|ts|jsx|tsx|json|md|html|css))['\"]?$",
            r"(?:tell me about|describe)\s+(?:the\s+)?(?:file\s+)?['\"]?([^'\"\s]+\.(?:py|js|ts|jsx|tsx|json|md|html|css))['\"]?$",
        ]
        
        for pattern in summary_patterns:
            summary_match = re.search(pattern, msg, re.IGNORECASE)
            if summary_match:
                filepath = summary_match.group(1).strip()
                return ToolCall("get_file_summary", {"filepath": filepath})
        
        return None
    
    def _git_fallback_tool_call(self, user_message: str):
        """Deterministic fallback for Git commands."""
        msg = user_message.strip()
        lower = msg.lower()
        
        # Look for repo path patterns (default to current workspace root)
        path_match = re.search(r"(?:in|from|at)\s+['\"]?([^'\"]+\.git|[^'\"]+/repo[^'\"]*|[^'\"]+/project[^'\"]*)['\"]?", msg, re.IGNORECASE)
        repo_path = path_match.group(1).strip() if path_match else "."
        
        # Handle git status
        if any(phrase in lower for phrase in ["git status", "repo status", "repository status", "check status"]):
            return ToolCall("git_status", {"repo_path": repo_path})
        
        # Handle git log — require "git log" explicitly to avoid matching words like "dialog", "catalog"
        log_match = re.search(r"git\s+log(?:\s+history)?(?:\s+for)?\s+(.+)?", msg, re.IGNORECASE)
        if log_match or "commit history" in lower:
            return ToolCall("git_log", {"repo_path": repo_path, "n": 10})
        
        # Handle git diff
        if any(phrase in lower for phrase in ["git diff", "show changes", "what changed", "unstaged", "staged changes"]):
            staged = "staged" in lower or "committed" in lower
            return ToolCall("git_diff", {"repo_path": repo_path, "staged": staged})
        
        # Handle git add — require "git add" explicitly to avoid matching "add a feature/timeout/etc."
        add_match = re.search(r"git\s+add\s+(?:file\s+)?['\"]?([^'\"]+)['\"]?", msg, re.IGNORECASE)
        if add_match:
            files = add_match.group(1).strip()
            return ToolCall("git_add", {"repo_path": repo_path, "files": files})
        
        # Handle git commit

        
        commit_match = re.search(r"(?:git\s+)?commit\s+(?:with\s+message\s+)?['\"]([^'\"]+)['\"]", msg, re.IGNORECASE)
        if commit_match or "commit changes" in lower:
            message = commit_match.group(1).strip() if commit_match else "Update from Jarvis"
            return ToolCall("git_commit", {"repo_path": repo_path, "message": message})
        
        # Handle git push
        if "git push" in lower or "push changes" in lower or "push to remote" in lower:
            return ToolCall("git_push", {"repo_path": repo_path})
        
        # Handle git pull
        if "git pull" in lower or "pull changes" in lower or "pull from remote" in lower:
            return ToolCall("git_pull", {"repo_path": repo_path})
        
        # Handle git checkout / switch branch
        checkout_match = re.search(r"(?:git\s+)?(?:checkout|switch\s+to)\s+(?:branch\s+)?['\"]?([^'\"\s]+)['\"]?", msg, re.IGNORECASE)
        if checkout_match:
            branch = checkout_match.group(1).strip()
            return ToolCall("git_checkout", {"repo_path": repo_path, "branch": branch})
        
        # Handle create branch
        create_branch_match = re.search(r"(?:create|make)\s+(?:new\s+)?branch\s+(?:called\s+)?['\"]?([^'\"\s]+)['\"]?", msg, re.IGNORECASE)
        if create_branch_match:
            branch = create_branch_match.group(1).strip()
            return ToolCall("git_create_branch", {"repo_path": repo_path, "branch": branch})
        
        return None

    def _system_fallback_tool_call(self, user_message: str):
        """Deterministic fallback for system/time requests."""
        lower = user_message.strip().lower()

        if any(phrase in lower for phrase in ["what time is it", "current time", "time now", "tell me the time"]):
            return ToolCall("get_time", {})

        if any(phrase in lower for phrase in ["system info", "cpu usage", "ram usage", "memory usage"]):
            return ToolCall("get_system_info", {})

        return None
    
    def _twitter_fallback_tool_call(self, user_message: str):
        """Deterministic fallback for Twitter/X requests."""
        msg = user_message.strip()
        lower = msg.lower()
        
        # Handle post tweet
        post_patterns = [
            r"(?:post|send)\s+(?:a\s+)?tweet(?:\s+|:\s*)(?:saying|that says|with|about)?\s*['\"]?([^'\"]+)['\"]?",
            r"tweet(?:\s+|:\s*)['\"]?([^'\"]+)['\"]?",
        ]
        for pattern in post_patterns:
            match = re.search(pattern, msg, re.IGNORECASE)
            if match:
                text = match.group(1).strip()
                return ToolCall("post_tweet", {"text": text})
        
        # Handle get timeline
        if any(phrase in lower for phrase in ["twitter timeline", "home timeline", "my feed", "twitter feed", "what's on twitter"]):
            return ToolCall("get_home_timeline", {"count": 10})
        
        # Handle search tweets
        search_match = re.search(r"(?:search twitter|search tweets|find on twitter|twitter search)\s+(?:for\s+)?['\"]?([^'\"]+)['\"]?", msg, re.IGNORECASE)
        if search_match:
            query = search_match.group(1).strip()
            return ToolCall("search_tweets", {"query": query, "count": 10})
        
        # Handle get user tweets
        user_match = re.search(r"(?:get tweets from|tweets from|twitter user|user)\s+@?([a-zA-Z0-9_]+)", msg, re.IGNORECASE)
        if user_match:
            username = user_match.group(1).strip()
            return ToolCall("get_user_tweets", {"username": username, "count": 10})
        
        # Handle delete tweet
        delete_match = re.search(r"(?:delete|remove)\s+(?:tweet\s+)?(?:id\s+)?['\"]?([0-9]+)['\"]?", msg, re.IGNORECASE)
        if delete_match and ("tweet" in lower or "twitter" in lower):
            tweet_id = delete_match.group(1).strip()
            return ToolCall("delete_tweet", {"tweet_id": tweet_id})
        
        return None
    
    def _get_codebase_context(self, user_message: str) -> str:
        """Search codebase index and return relevant context."""
        try:
            from app.tools.system_tools import execute_tool
            result = execute_tool("search_codebase", {"query": user_message, "n_results": 3})
            if "No results" not in result and "Error" not in result:
                return f"\n\nRelevant code from your codebase:\n{result}"
        except Exception:
            pass
        return ""
    
    def run(self, user_message: str, history: list, system_prompt: str) -> str:
        """Run the autonomous agent loop with error handling."""
        try:
            self.steps = 0
            self.tool_calls = 0
            self.observations = []

            smalltalk = self._smalltalk_direct_response(user_message)
            if smalltalk is not None:
                logger.info("[AGENT] Direct response: smalltalk")
                return smalltalk

            # Deterministic fast-path for explicit actions.
            direct_call = (self._code_fallback_tool_call(user_message) or
                          self._system_fallback_tool_call(user_message) or
                          self._clipboard_fallback_tool_call(user_message) or
                          self._screenshot_fallback_tool_call(user_message) or
                          self._calendar_fallback_tool_call(user_message) or
                          self._gmail_fallback_tool_call(user_message) or
                          self._codebase_fallback_tool_call(user_message) or
                          self._git_fallback_tool_call(user_message) or
                          self._twitter_fallback_tool_call(user_message) or
                          self._browser_fallback_tool_call(user_message) or 
                          self._notification_fallback_tool_call(user_message))
            if direct_call is not None:
                direct_result, _ = self._execute_tool_if_valid(direct_call.tool, direct_call.args)
                logger.info(f"[AGENT] Direct action: {direct_call.tool}")
                return str(direct_result)
            
            # Inject codebase context for coding questions
            from app.llm.router import classify_intent
            if classify_intent(user_message) == "coding":
                codebase_context = self._get_codebase_context(user_message)
                if codebase_context:
                    system_prompt = system_prompt + codebase_context
                    logger.info("[AGENT] Injected codebase context for coding query")
            
            # Add initial user message to history for this run
            run_history = history.copy()
            
            while self.steps < MAX_STEPS:
                self.steps += 1
                
                # Think about current state
                action_list = self.think(run_history, system_prompt)
                
                had_tool_call = False
                
                for action in action_list:
                    # Check if model wants to use a tool
                    if isinstance(action, ToolCall):
                        if self.tool_calls >= MAX_TOOL_CALLS:
                            logger.info(f"[AGENT] Max tool calls reached")
                            break
                        
                        tool_name = action.tool
                        tool_args = action.args
                        
                        # Execute tool
                        tool_result, executed = self._execute_tool_if_valid(tool_name, tool_args)
                        if not executed:
                            continue
                        self.tool_calls += 1
                        had_tool_call = True
                        
                        # Add observation
                        observation = f"Observation from {tool_name}: {tool_result}"
                        # Error recovery: explicitly tell the agent the call failed and it must fix it
                        result_str = str(tool_result)
                        if result_str.startswith("Error") or result_str.lower().startswith("error"):
                            observation += (
                                "\n\nThis tool call failed. Analyze the error message carefully, "
                                "identify what went wrong, and try a different approach to complete the original task."
                            )
                        self.observations.append(observation)

                        # Add to history for next iteration
                        run_history.append({
                            "role": "assistant",
                            "content": f"[Called {tool_name}]"
                        })
                        run_history.append({
                            "role": "user",
                            "content": observation
                        })
                        
                        logger.info(f"[AGENT] Step {self.steps}: Called {tool_name}, got: {str(tool_result)[:50]}...")
                    
                    # Check if model is done
                    elif isinstance(action, Response):
                        recovered_call = self._extract_tool_call_from_text(action.message)
                        if recovered_call is not None and self.tool_calls < MAX_TOOL_CALLS:
                            tool_result, executed = self._execute_tool_if_valid(recovered_call.tool, recovered_call.args)
                            if not executed:
                                continue
                            self.tool_calls += 1
                            had_tool_call = True
                            observation = f"Observation from {recovered_call.tool}: {tool_result}"
                            self.observations.append(observation)
                            run_history.append({"role": "assistant", "content": f"[Called {recovered_call.tool}]"})
                            run_history.append({"role": "user", "content": observation})
                            logger.info(f"[AGENT] Step {self.steps}: Recovered tool call {recovered_call.tool}")
                            continue

                        if action.is_done():
                            if self.tool_calls == 0:
                                fallback_call = (self._code_fallback_tool_call(user_message) or
                                               self._system_fallback_tool_call(user_message) or
                                               self._clipboard_fallback_tool_call(user_message) or
                                               self._screenshot_fallback_tool_call(user_message) or
                                               self._calendar_fallback_tool_call(user_message) or
                                               self._gmail_fallback_tool_call(user_message) or
                                               self._codebase_fallback_tool_call(user_message) or
                                               self._git_fallback_tool_call(user_message) or
                                               self._twitter_fallback_tool_call(user_message) or
                                               self._browser_fallback_tool_call(user_message) or 
                                               self._notification_fallback_tool_call(user_message))
                                if fallback_call is not None:
                                    tool_result, _ = self._execute_tool_if_valid(fallback_call.tool, fallback_call.args)
                                    self.tool_calls += 1
                                    logger.info(f"[AGENT] Step {self.steps}: Fallback called {fallback_call.tool} before done")
                                    return str(tool_result)
                            logger.info(f"[AGENT] Step {self.steps}: Task complete")
                            return action.message
                
                # If we had tool calls, add continuation prompt and continue the loop
                if had_tool_call:
                    # Remind the model of the original task and ask if more tools are needed
                    remaining_steps = MAX_STEPS - self.steps
                    remaining_tools = MAX_TOOL_CALLS - self.tool_calls
                    continuation = (
                        f"Remember the original request: \"{user_message}\". "
                        f"You have {remaining_steps} steps and {remaining_tools} tool calls remaining. "
                        f"If you have all the information needed now, provide your final answer with state \"done\". "
                        f"If you need more information, call another tool."
                    )
                    run_history.append({
                        "role": "user",
                        "content": continuation
                    })
                    continue
                
                # If no tool calls were made in this step, we have a response — return it
                if not had_tool_call:
                    if self.tool_calls == 0:
                        fallback_call = (self._code_fallback_tool_call(user_message) or
                                       self._system_fallback_tool_call(user_message) or
                                       self._clipboard_fallback_tool_call(user_message) or
                                       self._screenshot_fallback_tool_call(user_message) or
                                       self._calendar_fallback_tool_call(user_message) or
                                       self._gmail_fallback_tool_call(user_message) or
                                       self._codebase_fallback_tool_call(user_message) or
                                       self._git_fallback_tool_call(user_message) or
                                       self._twitter_fallback_tool_call(user_message) or
                                       self._browser_fallback_tool_call(user_message) or 
                                       self._notification_fallback_tool_call(user_message))
                        if fallback_call is not None:
                            tool_result, _ = self._execute_tool_if_valid(fallback_call.tool, fallback_call.args)
                            self.tool_calls += 1
                            logger.info(f"[AGENT] Step {self.steps}: Fallback called {fallback_call.tool}")
                            return str(tool_result)
                    for action in action_list:
                        if isinstance(action, Response):
                            recovered_call = self._extract_tool_call_from_text(action.message)
                            if recovered_call is not None and self.tool_calls < MAX_TOOL_CALLS:
                                tool_result, executed = self._execute_tool_if_valid(recovered_call.tool, recovered_call.args)
                                if not executed:
                                    continue
                                self.tool_calls += 1
                                logger.info(f"[AGENT] Step {self.steps}: Recovered tool call {recovered_call.tool}")
                                return str(tool_result)
                            logger.info(f"[AGENT] Step {self.steps}: Returning response")
                            return action.message
            
            # Max steps reached - ask model for final summary
            if self.observations:
                run_history.append({
                    "role": "user",
                    "content": "You've reached the step limit. Based on all observations above, provide your final answer now with state \"done\"."
                })
                final_action_list = self.think(run_history, system_prompt)
                for action in final_action_list:
                    if isinstance(action, Response):
                        return action.message
                return str([a.to_dict() for a in final_action_list])
            
            return "I reached my thinking limit. Please provide more specific guidance."
        
        except Exception as e:
            logger.error(f"Agent run failed: {str(e)}", exc_info=True)
            return f"I encountered an error while processing your request: {str(e)}"
