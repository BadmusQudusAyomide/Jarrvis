"""Deterministic user profile storage by session with selective context injection."""
import json
import re
from pathlib import Path
from threading import Lock
from datetime import datetime

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
PROFILE_DB = DATA_DIR / "profiles.json"
_LOCK = Lock()

# All known profile fields (besides notes and system fields)
PROFILE_FIELDS = [
    "name", "nickname", "location", "profession", "work",
    "current_project", "learning", "goals", "interests",
    "communication_style", "preferences", "timezone",
]


def _load_profiles() -> dict:
    if not PROFILE_DB.exists():
        return {}
    try:
        return json.loads(PROFILE_DB.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_profiles(data: dict) -> None:
    PROFILE_DB.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def extract_name(message: str) -> str | None:
    """Extract name from common patterns like 'my name is ...'."""
    if not message:
        return None
    msg = message.strip()
    patterns = [
        r"\bmy name is\s+([a-zA-Z][a-zA-Z\s'\-]{1,80})$",
        r"\bi am\s+([a-zA-Z][a-zA-Z\s'\-]{1,80})$",
        r"\bi'm\s+([a-zA-Z][a-zA-Z\s'\-]{1,80})$",
    ]
    for pattern in patterns:
        m = re.search(pattern, msg, flags=re.IGNORECASE)
        if m:
            name = re.sub(r"\s+", " ", m.group(1)).strip(" .,!?:;")
            if len(name) >= 2:
                return name.title()
    return None


def set_profile_name(session_id: str, name: str) -> None:
    with _LOCK:
        data = _load_profiles()
        profile = data.get(session_id, {})
        profile["name"] = name
        data[session_id] = profile
        _save_profiles(data)


def get_profile_name(session_id: str) -> str | None:
    with _LOCK:
        data = _load_profiles()
        profile = data.get(session_id, {})
        name = profile.get("name")
        return name if isinstance(name, str) and name.strip() else None


def clear_profile(session_id: str) -> None:
    with _LOCK:
        data = _load_profiles()
        if session_id in data:
            del data[session_id]
            _save_profiles(data)


def get_profile(session_id: str) -> dict:
    with _LOCK:
        data = _load_profiles()
        profile = data.get(session_id, {})
        if not isinstance(profile, dict):
            return {}
        return profile


def update_profile(session_id: str, updates: dict) -> dict:
    with _LOCK:
        data = _load_profiles()
        profile = data.get(session_id, {})
        if not isinstance(profile, dict):
            profile = {}

        for key, value in updates.items():
            if value is None:
                continue
            if key == "notes" and isinstance(value, list):
                existing = profile.get("notes", [])
                if not isinstance(existing, list):
                    existing = []
                for item in value:
                    if isinstance(item, str) and item.strip():
                        existing.append(item.strip())
                profile["notes"] = existing[-25:]
            elif key in ("goals", "interests") and isinstance(value, list):
                existing = profile.get(key, [])
                if not isinstance(existing, list):
                    existing = []
                for item in value:
                    if isinstance(item, str) and item.strip() and item.strip() not in existing:
                        existing.append(item.strip())
                profile[key] = existing[-10:]
            elif isinstance(value, str):
                profile[key] = value.strip()
            else:
                profile[key] = value

        profile["updated_at"] = datetime.now().isoformat()
        data[session_id] = profile
        _save_profiles(data)
        return profile


def set_pending_confirmation(session_id: str, field: str, new_value: str, old_value: str | None) -> dict:
    with _LOCK:
        data = _load_profiles()
        profile = data.get(session_id, {})
        if not isinstance(profile, dict):
            profile = {}
        profile["pending_confirmation"] = {
            "field": field,
            "new_value": new_value,
            "old_value": old_value,
            "created_at": datetime.now().isoformat(),
        }
        data[session_id] = profile
        _save_profiles(data)
        return profile


def get_pending_confirmation(session_id: str) -> dict | None:
    profile = get_profile(session_id)
    pending = profile.get("pending_confirmation")
    return pending if isinstance(pending, dict) else None


def clear_pending_confirmation(session_id: str) -> dict:
    with _LOCK:
        data = _load_profiles()
        profile = data.get(session_id, {})
        if not isinstance(profile, dict):
            profile = {}
        profile.pop("pending_confirmation", None)
        data[session_id] = profile
        _save_profiles(data)
        return profile


def apply_pending_confirmation(session_id: str) -> tuple[bool, str]:
    with _LOCK:
        data = _load_profiles()
        profile = data.get(session_id, {})
        if not isinstance(profile, dict):
            profile = {}
        pending = profile.get("pending_confirmation")
        if not isinstance(pending, dict):
            return False, "No pending confirmation."

        field = str(pending.get("field", "")).strip()
        new_value = str(pending.get("new_value", "")).strip()
        if not field or not new_value:
            profile.pop("pending_confirmation", None)
            data[session_id] = profile
            _save_profiles(data)
            return False, "Pending confirmation was invalid and has been cleared."

        profile[field] = new_value
        profile["updated_at"] = datetime.now().isoformat()
        profile.pop("pending_confirmation", None)
        data[session_id] = profile
        _save_profiles(data)
        return True, f"Updated {field.replace('_', ' ')} to '{new_value}'."


def add_profile_note(session_id: str, note: str) -> dict:
    return update_profile(session_id, {"notes": [note]})


def remove_profile_note(session_id: str, note_text: str) -> dict:
    with _LOCK:
        data = _load_profiles()
        profile = data.get(session_id, {})
        notes = profile.get("notes", [])
        if not isinstance(notes, list):
            notes = []
        cleaned = [n for n in notes if str(n).strip().lower() != note_text.strip().lower()]
        profile["notes"] = cleaned
        profile["updated_at"] = datetime.now().isoformat()
        data[session_id] = profile
        _save_profiles(data)
        return profile


def extract_profile_updates(message: str) -> dict:
    msg = message.strip()
    updates = {}

    name = extract_name(msg)
    if name:
        updates["name"] = name

    # Nickname / call me
    m = re.search(r"\b(?:call me|my nickname is)\s+([a-zA-Z][a-zA-Z\s'\-]{0,30})$", msg, re.IGNORECASE)
    if m:
        updates["nickname"] = m.group(1).strip(" .,!?:;")

    # Preferences
    m = re.search(r"\bi (?:prefer|like)\s+(.+)$", msg, re.IGNORECASE)
    if m:
        updates["preferences"] = m.group(1).strip(" .,!?:;")

    # Current project
    m = re.search(r"\bi(?:'m| am)\s+building\s+(.+)$", msg, re.IGNORECASE)
    if m:
        updates["current_project"] = m.group(1).strip(" .,!?:;")

    # Learning
    m = re.search(r"\bi(?:'m| am)\s+learning\s+(.+)$", msg, re.IGNORECASE)
    if m:
        updates["learning"] = m.group(1).strip(" .,!?:;")

    # Work / study
    m = re.search(r"\bi (?:work|study)\s+(.+)$", msg, re.IGNORECASE)
    if m:
        updates["work"] = m.group(1).strip(" .,!?:;")

    # Location
    m = re.search(r"\bi(?:'m| am)\s+based\s+in\s+(.+)$", msg, re.IGNORECASE)
    if m:
        updates["location"] = m.group(1).strip(" .,!?:;")
    if "location" not in updates:
        m = re.search(r"\bi\s+live\s+in\s+(.+)$", msg, re.IGNORECASE)
        if m:
            updates["location"] = m.group(1).strip(" .,!?:;")
    if "location" not in updates:
        m = re.search(r"\bi(?:'m| am)\s+from\s+([A-Z][a-zA-Z\s,]+)$", msg)
        if m:
            updates["location"] = m.group(1).strip(" .,!?:;")

    # Profession
    m = re.search(r"\bi\s+work\s+as\s+(?:a\s+|an\s+)?(.+)$", msg, re.IGNORECASE)
    if m:
        updates["profession"] = m.group(1).strip(" .,!?:;")
    if "profession" not in updates:
        profession_keywords = [
            "developer", "engineer", "student", "designer", "teacher", "doctor",
            "manager", "analyst", "scientist", "writer", "artist", "researcher",
            "programmer", "coder", "founder", "entrepreneur", "consultant", "nurse",
        ]
        m = re.search(r"\bi(?:'m| am)\s+(?:a|an)\s+(.+?)(?:\s+and\b|\s+who\b|\s+that\b|[.,!?]|$)", msg, re.IGNORECASE)
        if m:
            candidate = m.group(1).strip(" .,!?:;")
            if any(kw in candidate.lower() for kw in profession_keywords):
                updates["profession"] = candidate

    # Goals
    m = re.search(r"\bmy\s+goal\s+is\s+(?:to\s+)?(.+)$", msg, re.IGNORECASE)
    if m:
        updates["goals"] = [m.group(1).strip(" .,!?:;")]

    # Interests / hobbies
    m = re.search(r"\bmy\s+(?:interests?|hobbies)\s+(?:are|is)\s+(.+)$", msg, re.IGNORECASE)
    if m:
        updates["interests"] = [i.strip() for i in re.split(r",\s*|\s+and\s+", m.group(1)) if i.strip()]
    if "interests" not in updates:
        m = re.search(r"\bi(?:'m| am)\s+interested\s+in\s+(.+)$", msg, re.IGNORECASE)
        if m:
            updates["interests"] = [i.strip() for i in re.split(r",\s*|\s+and\s+", m.group(1)) if i.strip()]

    # Communication style
    if re.search(r"\bspeak\s+casually|be\s+casual|talk\s+casually|casual\s+mode", msg, re.IGNORECASE):
        updates["communication_style"] = "casual"
    elif re.search(r"\bspeak\s+formally|be\s+formal|talk\s+formally|formal\s+mode", msg, re.IGNORECASE):
        updates["communication_style"] = "formal"

    return updates


def build_persona_header(profile: dict) -> str:
    """Minimal always-on context: just name and tone.
    Everything else (goals, profession, project, interests) is handled by
    build_profile_context_for_message which only injects what's relevant to
    the current message, keeping token usage low.
    """
    if not profile:
        return ""

    parts = []

    name = profile.get("nickname") or profile.get("name")
    if name:
        parts.append(f"You are talking to {name}.")

    style = str(profile.get("communication_style", "")).lower()
    if "casual" in style:
        parts.append("Talk to them like a close friend — natural, direct, no fluff.")
    elif "formal" in style:
        parts.append("Use professional, formal communication.")

    if not parts:
        return ""

    return "\n\nUser: " + " ".join(parts) + "\n"


def build_full_profile_summary(profile: dict) -> str:
    """Build a readable summary of everything Jarvis knows about the user. Used by /whoami."""
    if not profile:
        return "I don't have any profile information yet. Tell me about yourself!"

    field_labels = {
        "name": "Name",
        "nickname": "Nickname",
        "location": "Location",
        "profession": "Profession",
        "work": "Work / Study",
        "current_project": "Currently Building",
        "learning": "Currently Learning",
        "goals": "Goals",
        "interests": "Interests / Hobbies",
        "communication_style": "Communication Style",
        "preferences": "Preferences",
        "timezone": "Timezone",
    }

    lines = ["Here's everything I know about you:"]
    for field, label in field_labels.items():
        value = profile.get(field)
        if value is None:
            continue
        if isinstance(value, list) and value:
            lines.append(f"- {label}: {', '.join(str(v) for v in value)}")
        elif isinstance(value, str) and value.strip():
            lines.append(f"- {label}: {value.strip()}")

    notes = profile.get("notes", [])
    if isinstance(notes, list) and notes:
        lines.append("- Notes: " + " | ".join(str(n) for n in notes[-5:]))

    if len(lines) == 1:
        return "I don't have much on you yet. Run /setup to fill in your profile, or just chat with me and I'll learn as we go."

    lines.append("\nUse /setup to update your profile anytime.")
    return "\n".join(lines)


def _tokenize(text: str) -> set:
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if len(t) > 2}


def build_profile_context_for_message(profile: dict, message: str, max_lines: int = 8) -> str:
    """Return profile facts relevant to the current message."""
    if not profile:
        return ""

    lines = []
    list_fields = {"goals", "interests"}

    for field in PROFILE_FIELDS:
        value = profile.get(field)
        if value is None:
            continue
        if field in list_fields and isinstance(value, list) and value:
            lines.append((field, f"{field.replace('_', ' ').title()}: {', '.join(str(v) for v in value)}"))
        elif isinstance(value, str) and value.strip():
            lines.append((field, f"{field.replace('_', ' ').title()}: {value.strip()}"))

    notes = profile.get("notes", [])
    if isinstance(notes, list):
        for note in notes[-10:]:
            if isinstance(note, str) and note.strip():
                lines.append(("note", f"Note: {note.strip()}"))

    if not lines:
        return ""

    query_tokens = _tokenize(message)
    query = message.lower()
    field_boost = {
        "name": any(k in query for k in ["name", "who am i"]),
        "nickname": any(k in query for k in ["name", "call me", "nickname"]),
        "location": any(k in query for k in ["location", "where", "based", "city", "country"]),
        "profession": any(k in query for k in ["job", "work", "profession", "career"]),
        "preferences": any(k in query for k in ["prefer", "preference", "like"]),
        "current_project": any(k in query for k in ["project", "building", "build"]),
        "learning": any(k in query for k in ["learn", "learning", "study"]),
        "work": any(k in query for k in ["work", "job", "career"]),
        "timezone": any(k in query for k in ["time zone", "timezone", "time"]),
        "goals": any(k in query for k in ["goal", "want", "aim", "achieve"]),
        "interests": any(k in query for k in ["interest", "hobby", "hobbies", "enjoy"]),
        "communication_style": any(k in query for k in ["talk", "style", "formal", "casual"]),
    }

    scored = []
    for key, line in lines:
        line_tokens = _tokenize(line)
        overlap = len(query_tokens.intersection(line_tokens))
        bias = 2 if key == "name" else 0
        if field_boost.get(key, False):
            bias += 3
        scored.append((overlap + bias, line))

    scored.sort(key=lambda x: x[0], reverse=True)
    selected = [line for score, line in scored if score > 0][:max_lines]

    if not selected:
        name = profile.get("nickname") or profile.get("name")
        if isinstance(name, str) and name.strip():
            selected = [f"Name: {name.strip()}"]

    if not selected:
        return ""

    return "\nUser profile facts:\n" + "\n".join(f"- {line}" for line in selected) + "\n"
