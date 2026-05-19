import json
import re
import logging
from app.agents.actions import ActionFactory, Response, ToolCall
from app.tools.system_tools import TOOLS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def parse_model_output(text: str):
    """Parse model output as JSON, with fallback for plain text."""
    try:
        data = json.loads(text)
        return ActionFactory.from_dict(data)
    except json.JSONDecodeError:
        try:
            repaired = text.replace("\\'", "'")
            data = json.loads(repaired)
            return ActionFactory.from_dict(data)
        except json.JSONDecodeError:
            pass
        logger.warning(f"Failed to parse JSON, treating as plain text: {text[:100]}...")
        # Model ignored instructions, treat as normal response
        return Response(message=text)

def _resolve_thinking_model_text(text: str) -> str:
    """Handle <think>...</think> blocks from reasoning models (qwen-qwq, deepseek-r1).

    Strategy:
    1. If content after </think> contains JSON → use that (normal case).
    2. If content after </think> has no JSON → check inside <think> for JSON
       (some qwen variants put the tool call inside the reasoning block).
    3. Fallback: return the post-think text as-is (plain response).
    """
    if "</think>" not in text:
        return text

    post_think = text.split("</think>", 1)[1].strip()

    if post_think and "{" in post_think:
        return post_think

    think_match = re.search(r"<think>(.*?)</think>", text, re.DOTALL)
    if think_match:
        inside = think_match.group(1)
        if "{" in inside:
            return inside

    return post_think if post_think else text


def parse_all_model_outputs(text: str) -> list:
    """Parse all JSON objects from model output, handling multiple tool calls."""
    results = []

    # Handle reasoning models (qwen-qwq, deepseek-r1) that wrap output in <think> tags.
    # Some put the JSON tool call after </think>, some put it inside — handle both.
    text = _resolve_thinking_model_text(text)

    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.IGNORECASE)
        stripped = re.sub(r"\s*```$", "", stripped)

    # Fast path for single full JSON payload.
    try:
        data = json.loads(stripped)
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    results.append(ActionFactory.from_dict(item))
            if results:
                return results
        elif isinstance(data, dict):
            return [ActionFactory.from_dict(data)]
    except json.JSONDecodeError:
        try:
            data = json.loads(stripped.replace("\\'", "'"))
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        results.append(ActionFactory.from_dict(item))
                if results:
                    return results
            elif isinstance(data, dict):
                return [ActionFactory.from_dict(data)]
        except json.JSONDecodeError:
            pass
    
    # Try to find all JSON objects using regex
    # Match { ... } patterns, including nested braces
    brace_depth = 0
    start = None
    
    for i, char in enumerate(text):
        if char == '{':
            if brace_depth == 0:
                start = i
            brace_depth += 1
        elif char == '}':
            brace_depth -= 1
            if brace_depth == 0 and start is not None:
                json_str = text[start:i+1]
                try:
                    parsed = json.loads(json_str)
                    action = ActionFactory.from_dict(parsed)
                    results.append(action)
                    logger.info(f"Successfully parsed action: {type(action).__name__}")
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse JSON object: {e}")
                    pass
                except Exception as e:
                    logger.warning(f"Failed to create action from JSON: {e}")
                    pass
                start = None
    
    # If no JSON objects found, treat entire text as a response
    if not results:
        # Heuristic fallback for model outputs like:
        # "[Called browser_open] with url https://google.com"
        # "[Called browser_fill] with selector q and text hello world"
        call_match = re.search(r"\[Called\s+([a-zA-Z0-9_]+)\]", text)
        if call_match:
            tool_name = call_match.group(1)
            if tool_name not in TOOLS:
                logger.warning(f"Ignoring fallback tool call for unknown tool: {tool_name}")
                results.append(Response(message=text.strip()))
                return results
            args = {}

            if tool_name == "browser_open":
                m = re.search(r"with\s+url\s+(\S+)", text, re.IGNORECASE)
                if m:
                    args["url"] = m.group(1).strip()
            elif tool_name == "browser_fill":
                m = re.search(r"with\s+selector\s+(.+?)\s+and\s+text\s+(.+)$", text, re.IGNORECASE)
                if m:
                    args["selector"] = m.group(1).strip().strip("'\"")
                    args["text"] = m.group(2).strip().strip("'\"")
            elif tool_name in {"browser_click", "browser_get_text", "browser_get_html"}:
                m = re.search(r"with\s+selector\s+(.+)$", text, re.IGNORECASE)
                if m:
                    args["selector"] = m.group(1).strip().strip("'\"")
            elif tool_name == "browser_screenshot":
                m = re.search(r"with\s+filename\s+(.+)$", text, re.IGNORECASE)
                if m:
                    args["filename"] = m.group(1).strip().strip("'\"")

            results.append(ToolCall(tool=tool_name, args=args))
            logger.info(f"Parsed fallback tool call: {tool_name} args={args}")
            return results

        logger.warning(f"No valid JSON found, treating entire text as response: {text[:100]}...")
        results.append(Response(message=text.strip()))
    
    return results
