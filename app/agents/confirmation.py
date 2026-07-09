"""Session-scoped confirmation gate for destructive tool calls.

Mirrors the pending-confirmation pattern already used for profile name
updates (app/memory/profile.py) but for tool calls whose effects are hard to
undo or visible outside this machine (shell commands, deleting files,
pushing to a remote, sending email/tweets, killing processes).
"""
import json
import logging
from datetime import datetime
from pathlib import Path
from threading import Lock

logger = logging.getLogger(__name__)

_STORE_PATH = Path("data/pending_actions.json")
_LOCK = Lock()

DESTRUCTIVE_TOOLS = {
    "execute_command",
    "delete_file",
    "move_rename",
    "git_push",
    "kill_process",
    "send_email",
    "post_tweet",
    "delete_tweet",
}


def _load() -> dict:
    if not _STORE_PATH.exists():
        return {}
    try:
        return json.loads(_STORE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save(data: dict):
    _STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _STORE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def set_pending_action(session_id: str, tool_name: str, args: dict) -> dict:
    with _LOCK:
        data = _load()
        entry = {
            "tool": tool_name,
            "args": args,
            "created_at": datetime.now().isoformat(),
        }
        data[session_id] = entry
        _save(data)
        return entry


def get_pending_action(session_id: str) -> dict | None:
    with _LOCK:
        data = _load()
        entry = data.get(session_id)
        return entry if isinstance(entry, dict) else None


def clear_pending_action(session_id: str):
    with _LOCK:
        data = _load()
        data.pop(session_id, None)
        _save(data)


def describe_action(tool_name: str, args: dict) -> str:
    """Human-readable one-liner for a confirmation prompt."""
    if not args:
        return tool_name
    parts = ", ".join(f"{k}={v!r}" for k, v in args.items())
    return f"{tool_name}({parts})"
