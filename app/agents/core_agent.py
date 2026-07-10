from app.llm.ollama import chat_with_tools
from app.tools.system_tools import execute_tool, TOOLS, get_tool_schemas, get_relevant_tool_names
from app.config import DEFAULT_MODEL
from app.agents.confirmation import DESTRUCTIVE_TOOLS, describe_action, set_pending_action
import logging
import json

logger = logging.getLogger(__name__)

MAX_STEPS = 8
MAX_TOOL_CALLS = 8

# Deliberately tiny and exact-match only — this is NOT a growing pile of
# regex patterns trying to catch every casual phrasing (that's the mistake
# the old 11-parser fallback system made). Anything not a literal match here
# falls through to the model; when in doubt, call the LLM, don't guess.
_SMALLTALK_RESPONSES = {
    "hi": "Hello! How can I help you today?",
    "hello": "Hello! How can I help you today?",
    "hey": "Hey! What can I do for you?",
    "yo": "Hey! What can I do for you?",
    "how are you": "I'm doing well, thanks for asking! How can I help you today?",
    "how are you doing": "I'm doing well, thanks for asking! How can I help you today?",
    "how's it going": "I'm doing well, thanks for asking! How can I help you today?",
    "thanks": "You're welcome!",
    "thank you": "You're welcome!",
    "thanks jarvis": "You're welcome!",
    "bye": "Goodbye! Talk soon.",
    "goodbye": "Goodbye! Talk soon.",
    "see you": "Goodbye! Talk soon.",
}


def _match_smalltalk(text: str) -> str | None:
    """Exact-match against a short allowlist only. No fuzzy matching, no
    substring/contains checks — a message that isn't a verbatim hit falls
    through to the model rather than risk misfiring on something that
    wasn't actually smalltalk."""
    normalized = text.strip().lower().rstrip("!.?")
    return _SMALLTALK_RESPONSES.get(normalized)


class Agent:
    def __init__(self, model: str = None):
        self.model = model or DEFAULT_MODEL
        self.steps = 0
        self.tool_calls = 0
        self.observations = []
        self._tool_schemas = []
        # Set whenever the most recent tool call failed and hasn't since been
        # followed by a successful one; None once the last attempt succeeded
        # (or no tool was ever called). Callers that need to know whether a
        # run actually succeeded — e.g. the plan orchestrator — should check
        # this instead of sniffing the model's final prose for the word
        # "error", since the model routinely paraphrases failures in its own
        # words rather than echoing the raw tool error.
        self.last_tool_error = None

    def _execute_tool_if_valid(self, tool_name: str, tool_args: dict):
        """Execute only registered tools and return tuple(result, executed)."""
        if tool_name not in TOOLS:
            logger.warning(f"[AGENT] Ignoring unknown tool request: {tool_name}")
            return f"Error: Unknown tool '{tool_name}'", False
        return execute_tool(tool_name, tool_args), True

    def think(self, history: list, system_prompt: str) -> dict:
        """Ask the model for its next move via native function calling.
        Returns the raw assistant message: {"content": ..., "tool_calls": [...]}."""
        try:
            return chat_with_tools(history, self._tool_schemas, model=self.model, system_prompt=system_prompt)
        except Exception as e:
            logger.error(f"Error in think method: {str(e)}", exc_info=True)
            return {"content": f"I encountered an error: {str(e)}"}

    def run(self, user_message: str, history: list, system_prompt: str, session_id: str = None) -> str:
        """Run the autonomous agent loop using native tool calling.

        session_id, when provided, lets destructive tool calls (see
        app.agents.confirmation.DESTRUCTIVE_TOOLS) pause and ask the user to
        confirm before running instead of executing immediately. Without a
        session_id (e.g. background/planned tasks with no one to ask), those
        calls are refused outright rather than run unsupervised.
        """
        try:
            self.steps = 0
            self.tool_calls = 0
            self.observations = []
            self.last_tool_error = None

            smalltalk_reply = _match_smalltalk(user_message)
            if smalltalk_reply is not None:
                logger.info(f"[AGENT] Smalltalk fast-path matched ({user_message!r}) — skipped LLM call")
                return smalltalk_reply

            self._tool_schemas = get_tool_schemas(get_relevant_tool_names(user_message))
            logger.info(f"[AGENT] Scoped to {len(self._tool_schemas)} tool schemas for this request")

            run_history = history.copy()

            while self.steps < MAX_STEPS:
                self.steps += 1

                message = self.think(run_history, system_prompt)
                tool_calls = message.get("tool_calls") or []

                if not tool_calls:
                    logger.info(f"[AGENT] Step {self.steps}: Task complete")
                    return message.get("content") or "I don't have a response for that."

                run_history.append({
                    "role": "assistant",
                    "content": message.get("content"),
                    "tool_calls": tool_calls,
                })

                for call in tool_calls:
                    if self.tool_calls >= MAX_TOOL_CALLS:
                        logger.info("[AGENT] Max tool calls reached")
                        break

                    fn = call.get("function", {})
                    tool_name = fn.get("name")
                    try:
                        tool_args = json.loads(fn.get("arguments") or "{}")
                    except json.JSONDecodeError:
                        tool_args = {}

                    if tool_name in DESTRUCTIVE_TOOLS:
                        if session_id is None:
                            tool_result = (
                                f"Error: '{tool_name}' is a destructive action and requires interactive "
                                "confirmation. It cannot run in this context (no active chat session to confirm with)."
                            )
                            self.tool_calls += 1
                            self.last_tool_error = tool_result
                            self.observations.append(f"Observation from {tool_name}: {tool_result}")
                            run_history.append({
                                "role": "tool",
                                "tool_call_id": call.get("id"),
                                "name": tool_name,
                                "content": tool_result,
                            })
                            logger.warning(f"[AGENT] Blocked destructive tool '{tool_name}' — no session_id")
                            continue

                        set_pending_action(session_id, tool_name, tool_args)
                        description = describe_action(tool_name, tool_args)
                        logger.info(f"[AGENT] Step {self.steps}: Awaiting confirmation for {description}")
                        provenance = (
                            "\n\n(This follows content from other tools I already ran this turn — "
                            "reply 'no' if you don't recognize this as something you asked for.)"
                            if self.tool_calls > 0 else ""
                        )
                        return (
                            f"I'd like to run: {description}\n\n"
                            "This action can't be easily undone, so I'm checking first — "
                            f"reply 'yes' to proceed or 'no' to cancel.{provenance}"
                        )

                    tool_result, executed = self._execute_tool_if_valid(tool_name, tool_args)
                    self.tool_calls += 1

                    result_str = str(tool_result)
                    if result_str.lower().startswith("error"):
                        self.last_tool_error = result_str
                        result_str += (
                            "\n\nThis tool call failed. Analyze the error message carefully, "
                            "identify what went wrong, and try a different approach to complete the original task."
                        )
                    else:
                        self.last_tool_error = None
                    self.observations.append(f"Observation from {tool_name}: {tool_result}")

                    run_history.append({
                        "role": "tool",
                        "tool_call_id": call.get("id"),
                        "name": tool_name,
                        "content": result_str,
                    })

                    logger.info(f"[AGENT] Step {self.steps}: Called {tool_name}, got: {str(tool_result)[:50]}...")

                if self.tool_calls >= MAX_TOOL_CALLS:
                    break

                remaining_tools = MAX_TOOL_CALLS - self.tool_calls
                run_history.append({
                    "role": "user",
                    "content": (
                        f"Remember the original request: \"{user_message}\". "
                        f"You have {remaining_tools} tool calls remaining. "
                        "If the observations above already answer the request, respond now in plain text "
                        "with your final answer — do not call any more tools. "
                        "Only call another tool if it's still needed to answer the original request."
                    ),
                })

            # Max steps (or max tool calls) reached — ask model for a final summary
            if self.observations:
                run_history.append({
                    "role": "user",
                    "content": "You've reached the step limit. Based on all observations above, provide your final answer now."
                })
                final_message = self.think(run_history, system_prompt)
                return final_message.get("content") or "I reached my thinking limit."

            return "I reached my thinking limit. Please provide more specific guidance."

        except Exception as e:
            logger.error(f"Agent run failed: {str(e)}", exc_info=True)
            self.last_tool_error = str(e)
            return f"I encountered an error while processing your request: {str(e)}"
