"""Reminder persistence for the Jarvis Telegram bot.
Stores reminders in data/reminders.json so they survive restarts.
The actual scheduling is done via python-telegram-bot's JobQueue.
"""
import json
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
REMINDERS_FILE = DATA_DIR / "reminders.json"


def load_reminders() -> list:
    if not REMINDERS_FILE.exists():
        return []
    try:
        return json.loads(REMINDERS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save_reminders(reminders: list) -> None:
    REMINDERS_FILE.write_text(json.dumps(reminders, ensure_ascii=False, indent=2), encoding="utf-8")


def save_reminder(user_id: int, chat_id: int, message: str, run_at: datetime) -> str:
    reminder_id = f"rem_{user_id}_{int(run_at.timestamp())}"
    reminders = load_reminders()
    reminders.append({
        "id": reminder_id,
        "user_id": user_id,
        "chat_id": chat_id,
        "message": message,
        "run_at": run_at.isoformat(),
    })
    _save_reminders(reminders)
    return reminder_id


def remove_reminder(reminder_id: str) -> None:
    reminders = [r for r in load_reminders() if r.get("id") != reminder_id]
    _save_reminders(reminders)


def get_user_reminders(user_id: int) -> list:
    now = datetime.now()
    return [
        r for r in load_reminders()
        if r.get("user_id") == user_id and datetime.fromisoformat(r["run_at"]) > now
    ]


def purge_expired_reminders() -> None:
    now = datetime.now()
    active = [r for r in load_reminders() if datetime.fromisoformat(r["run_at"]) > now]
    _save_reminders(active)


def parse_reminder_time(text: str) -> tuple:
    """Parse reminder text into (datetime | None, message | error_str).

    Supported formats:
      in 2 hours call mom
      in 30 minutes take a break
      at 6pm buy groceries
      at 9:30am team standup
      tomorrow at 8am check emails
    """
    now = datetime.now()
    text = text.strip()

    # "in X minutes/hours/days <message>"
    m = re.match(r"in\s+(\d+)\s+(minute|minutes|hour|hours|day|days)\s+(.+)", text, re.IGNORECASE)
    if m:
        amount, unit, message = int(m.group(1)), m.group(2).lower(), m.group(3).strip()
        delta = timedelta(minutes=amount) if "minute" in unit else (timedelta(hours=amount) if "hour" in unit else timedelta(days=amount))
        return now + delta, message

    # "tomorrow at HH:MM [am|pm] <message>"
    m = re.match(r"tomorrow\s+at\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s+(.+)", text, re.IGNORECASE)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2) or 0)
        ampm, message = (m.group(3) or "").lower(), m.group(4).strip()
        hour = _fix_hour(hour, ampm)
        run_at = (now + timedelta(days=1)).replace(hour=hour, minute=minute, second=0, microsecond=0)
        return run_at, message

    # "at HH:MM [am|pm] <message>"
    m = re.match(r"at\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s+(.+)", text, re.IGNORECASE)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2) or 0)
        ampm, message = (m.group(3) or "").lower(), m.group(4).strip()
        hour = _fix_hour(hour, ampm)
        run_at = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if run_at <= now:
            run_at += timedelta(days=1)
        return run_at, message

    return None, (
        "Could not parse reminder time. Try:\n"
        "  in 2 hours call mom\n"
        "  at 6pm buy groceries\n"
        "  at 9:30am standup\n"
        "  tomorrow at 8am check emails"
    )


def _fix_hour(hour: int, ampm: str) -> int:
    if ampm == "pm" and hour != 12:
        return hour + 12
    if ampm == "am" and hour == 12:
        return 0
    return hour
