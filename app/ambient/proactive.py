"""Ambient/proactive awareness loop.

Everything else in this codebase is reactive — it only ever runs in response
to an incoming message. This module is the one exception: called on a
schedule (see app/main.py), it checks calendar/email/system state on its own
and pushes a Telegram message when something is worth surfacing, without the
user ever asking. State (which events/emails have already been notified
about, alert cooldowns) is persisted to data/ambient_state.json so restarts
don't cause duplicate or missed notifications.
"""
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psutil
import requests
from googleapiclient.discovery import build

from app.utils.google_auth import get_google_credentials

logger = logging.getLogger(__name__)

STATE_FILE = Path("data/ambient_state.json")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
OWNER_CHAT_ID = os.getenv("OWNER_TELEGRAM_ID", "").strip()

CALENDAR_LOOKAHEAD_MINUTES = 15
DISK_FREE_ALERT_PERCENT = 10
RAM_ALERT_PERCENT = 90
ALERT_COOLDOWN_HOURS = 6

_DEFAULT_STATE = {
    "notified_event_ids": [],
    "seen_email_ids": [],
    "last_disk_alert": None,
    "last_ram_alert": None,
}


def _load_state() -> dict:
    if not STATE_FILE.exists():
        return dict(_DEFAULT_STATE)
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return {**_DEFAULT_STATE, **data}
    except Exception:
        return dict(_DEFAULT_STATE)


def _save_state(state: dict):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def send_owner_notification(text: str, dry_run: bool = False) -> bool:
    """Push a message to the owner's Telegram chat. dry_run logs instead of sending."""
    if dry_run:
        logger.info(f"[DRY RUN] Would send proactive notification: {text}")
        return True

    if not TELEGRAM_BOT_TOKEN or not OWNER_CHAT_ID or OWNER_CHAT_ID == "0":
        logger.warning("Cannot send proactive notification — TELEGRAM_BOT_TOKEN or OWNER_TELEGRAM_ID not set")
        return False
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": OWNER_CHAT_ID, "text": text},
            timeout=15,
        )
        if resp.status_code != 200:
            logger.error(f"Telegram send failed: {resp.status_code} {resp.text[:200]}")
        return resp.status_code == 200
    except Exception as e:
        logger.error(f"Failed to send proactive notification: {e}")
        return False


def check_calendar(state: dict) -> list[str]:
    """Notify about events starting within CALENDAR_LOOKAHEAD_MINUTES that
    haven't been notified about yet."""
    notifications = []
    try:
        creds = get_google_credentials()
        service = build("calendar", "v3", credentials=creds)
        now = datetime.now(timezone.utc)
        time_max = now + timedelta(minutes=CALENDAR_LOOKAHEAD_MINUTES)

        events_result = service.events().list(
            calendarId="primary",
            timeMin=now.isoformat(),
            timeMax=time_max.isoformat(),
            singleEvents=True,
            orderBy="startTime",
        ).execute()

        for event in events_result.get("items", []):
            event_id = event["id"]
            if event_id in state["notified_event_ids"]:
                continue
            start = event["start"].get("dateTime", event["start"].get("date"))
            if "T" not in start:
                continue  # all-day events aren't time-sensitive reminders
            start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
            minutes_until = (start_dt - now).total_seconds() / 60
            if 0 <= minutes_until <= CALENDAR_LOOKAHEAD_MINUTES:
                title = event.get("summary", "Untitled event")
                notifications.append(f"📅 Upcoming: \"{title}\" starts in {int(minutes_until)} min")
                state["notified_event_ids"].append(event_id)

        state["notified_event_ids"] = state["notified_event_ids"][-200:]
    except Exception as e:
        logger.error(f"Ambient calendar check failed: {e}")
    return notifications


def _judge_important_emails(details: list[dict]) -> list[dict]:
    """One cheap batched model call: which of these emails are worth
    interrupting the user for, vs. routine/promotional noise."""
    if not details:
        return []
    try:
        from app.llm.ollama import chat_with_tools

        listing = "\n".join(f"{i + 1}. From: {d['from']} | Subject: {d['subject']}" for i, d in enumerate(details))
        prompt = (
            "Here are new unread emails. Reply with ONLY the numbers (comma-separated) of "
            "emails that seem genuinely important or time-sensitive and worth interrupting "
            "the user for right now. Ignore newsletters, promotions, automated notifications, "
            "and routine updates. If none qualify, reply with exactly: none\n\n" + listing
        )
        message = chat_with_tools(
            [{"role": "user", "content": prompt}],
            tools=[],
            system_prompt="You are a filter. Output ONLY comma-separated numbers, or the word none. No explanation.",
        )
        content = (message.get("content") or "").strip().lower()
        if not content or content == "none":
            return []
        indices = [int(x.strip()) - 1 for x in content.replace(".", "").split(",") if x.strip().lstrip("-").isdigit()]
        return [details[i] for i in indices if 0 <= i < len(details)]
    except Exception as e:
        logger.error(f"Email importance judgment failed: {e}")
        return []


def check_email(state: dict) -> list[str]:
    """Notify about new unread emails the model judges worth surfacing."""
    notifications = []
    try:
        creds = get_google_credentials()
        service = build("gmail", "v1", credentials=creds)
        messages_result = service.users().messages().list(userId="me", q="is:unread", maxResults=10).execute()
        messages = messages_result.get("messages", [])

        new_messages = [m for m in messages if m["id"] not in state["seen_email_ids"]]
        if not new_messages:
            return notifications

        details = []
        for m in new_messages[:5]:
            msg = service.users().messages().get(
                userId="me", id=m["id"], format="metadata", metadataHeaders=["From", "Subject"]
            ).execute()
            headers = msg["payload"]["headers"]
            frm = next((h["value"] for h in headers if h["name"] == "From"), "Unknown")
            subject = next((h["value"] for h in headers if h["name"] == "Subject"), "No subject")
            details.append({"id": m["id"], "from": frm, "subject": subject})
            state["seen_email_ids"].append(m["id"])

        for item in _judge_important_emails(details):
            notifications.append(f"📧 New email from {item['from']}: \"{item['subject']}\"")

        state["seen_email_ids"] = state["seen_email_ids"][-500:]
    except Exception as e:
        logger.error(f"Ambient email check failed: {e}")
    return notifications


def check_system_health(state: dict) -> list[str]:
    """Rule-based, no model call — disk/RAM thresholds with a cooldown so
    a sustained condition doesn't spam a notification every tick."""
    notifications = []
    now = datetime.now()

    disk = psutil.disk_usage("C:\\" if os.name == "nt" else "/")
    free_percent = 100 - disk.percent
    if free_percent < DISK_FREE_ALERT_PERCENT:
        last = state.get("last_disk_alert")
        if not last or (now - datetime.fromisoformat(last)) > timedelta(hours=ALERT_COOLDOWN_HOURS):
            notifications.append(f"⚠️ Low disk space: only {free_percent:.1f}% free")
            state["last_disk_alert"] = now.isoformat()

    ram = psutil.virtual_memory()
    if ram.percent > RAM_ALERT_PERCENT:
        last = state.get("last_ram_alert")
        if not last or (now - datetime.fromisoformat(last)) > timedelta(hours=ALERT_COOLDOWN_HOURS):
            notifications.append(f"⚠️ High RAM usage: {ram.percent:.0f}%")
            state["last_ram_alert"] = now.isoformat()

    return notifications


def run_proactive_check(dry_run: bool = False) -> list[str]:
    """One tick of the ambient loop. Scheduled periodically from app/main.py."""
    state = _load_state()
    notifications = []

    try:
        notifications.extend(check_calendar(state))
    except Exception as e:
        logger.error(f"Calendar check crashed: {e}")
    try:
        notifications.extend(check_email(state))
    except Exception as e:
        logger.error(f"Email check crashed: {e}")
    try:
        notifications.extend(check_system_health(state))
    except Exception as e:
        logger.error(f"System health check crashed: {e}")

    for note in notifications:
        send_owner_notification(note, dry_run=dry_run)

    _save_state(state)
    if notifications:
        logger.info(f"Ambient check produced {len(notifications)} notification(s)")
    return notifications
