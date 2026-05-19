import logging
import os
import sys
import json
import asyncio
import tempfile
import requests
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# Ensure project root is on sys.path when running this file directly
_PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Backend URLs ---
# On Render the FastAPI server runs on $PORT (default 10000); locally it's 8080.
_PORT = os.getenv("PORT", "8080")
_BASE = f"http://127.0.0.1:{_PORT}"
API_URL              = f"{_BASE}/chat"
CLEAR_URL            = f"{_BASE}/chat/clear"
DOWNLOAD_URL         = f"{_BASE}/tools/download_media"
PROFILE_GET_URL      = f"{_BASE}/profile/get"
PROFILE_UPDATE_URL   = f"{_BASE}/profile/update"
PROFILE_REMEMBER_URL = f"{_BASE}/profile/remember"
PROFILE_FORGET_URL   = f"{_BASE}/profile/forget"

# Security: restrict to owner if set
OWNER_TELEGRAM_ID = int(os.getenv("OWNER_TELEGRAM_ID", "0"))

# --- Setup conversation states ---
(
    SETUP_NAME,
    SETUP_NICKNAME,
    SETUP_LOCATION,
    SETUP_PROFESSION,
    SETUP_PROJECT,
    SETUP_GOALS,
    SETUP_INTERESTS,
    SETUP_STYLE,
) = range(8)


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------

def _session_id(user_id: int) -> str:
    return f"telegram_{user_id}"


def _is_owner(user_id: int) -> bool:
    return OWNER_TELEGRAM_ID == 0 or user_id == OWNER_TELEGRAM_ID


def ask_jarvis(message: str, session_id: str) -> str:
    try:
        resp = requests.post(API_URL, json={"message": message, "session_id": session_id}, timeout=300)
        resp.raise_for_status()
        payload = resp.json().get("response", "No response")
        if isinstance(payload, (dict, list)):
            return json.dumps(payload, ensure_ascii=False)
        return str(payload)
    except requests.ConnectionError:
        return "Jarvis backend is not running. Start it first."
    except requests.Timeout:
        return "Request timed out. The operation may still be running."
    except Exception as e:
        logger.error(f"ask_jarvis error: {e}")
        return f"Error: {e}"


def _update_profile_api(session_id: str, updates: dict) -> None:
    try:
        requests.post(PROFILE_UPDATE_URL, json={"session_id": session_id, "updates": updates}, timeout=10)
    except Exception as e:
        logger.error(f"profile update error: {e}")


def _get_profile_api(session_id: str) -> dict:
    try:
        resp = requests.get(PROFILE_GET_URL, params={"session_id": session_id}, timeout=10)
        resp.raise_for_status()
        return resp.json().get("profile", {})
    except Exception:
        return {}


async def _keep_typing(bot, chat_id: int, stop_event: asyncio.Event) -> None:
    """Send typing indicator every 4 s until stop_event is set."""
    while not stop_event.is_set():
        try:
            await bot.send_chat_action(chat_id=chat_id, action="typing")
        except Exception:
            break
        try:
            await asyncio.wait_for(asyncio.shield(stop_event.wait()), timeout=4.0)
        except asyncio.TimeoutError:
            pass


async def _send_long(message, text: str) -> None:
    """Split and send text that may exceed Telegram's 4096-char limit."""
    MAX = 4096
    if len(text) <= MAX:
        await message.reply_text(text)
    else:
        for i in range(0, len(text), MAX):
            await message.reply_text(text[i : i + MAX])


async def _run_jarvis(update: Update, message: str, session_id: str) -> None:
    """Show typing, call Jarvis in a thread, send reply."""
    stop = asyncio.Event()
    typing = asyncio.create_task(_keep_typing(update.effective_message._bot, update.effective_chat.id, stop))
    try:
        response = await asyncio.to_thread(ask_jarvis, message, session_id)
    finally:
        stop.set()
        typing.cancel()
    await _send_long(update.effective_message, response)


# ---------------------------------------------------------------------------
# Standard commands
# ---------------------------------------------------------------------------

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await update.message.reply_text(
        f"Hey {user.first_name}! I'm Jarvis, your personal AI assistant.\n\n"
        "I can help you with almost anything. Just send me a message.\n\n"
        "Commands:\n"
        "/setup — Set up your profile (do this first!)\n"
        "/whoami — What I know about you\n"
        "/remember <text> — Save a note\n"
        "/forget <text> — Remove a note\n"
        "/remind <time> <message> — Set a reminder\n"
        "/reminders — List your pending reminders\n"
        "/briefing — Morning briefing (emails + calendar)\n"
        "/download <url> — Download media\n"
        "/clear — Clear conversation history\n"
        "/profile — Raw profile JSON\n"
        "/model — Check which AI model is active\n"
        "/help — Show this message\n\n"
        "You can also send voice messages and photos!"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await start_command(update, context)


async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    session_id = _session_id(user_id)
    try:
        resp = requests.post(CLEAR_URL, params={"session_id": session_id}, timeout=30)
        result = resp.json().get("message", "Session cleared.")
    except Exception as e:
        result = f"Error clearing: {e}"
    await update.message.reply_text(f"{result}\nFresh start!")


async def whoami_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    session_id = _session_id(user_id)
    response = await asyncio.to_thread(ask_jarvis, "what do you know about me", session_id)
    await _send_long(update.message, response)


async def remember_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    session_id = _session_id(user_id)
    text = " ".join(context.args).strip()
    if not text:
        await update.message.reply_text("Usage: /remember <text>")
        return
    try:
        requests.post(PROFILE_REMEMBER_URL, json={"session_id": session_id, "text": text}, timeout=10)
        await update.message.reply_text(f"Noted: {text}")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")


async def forget_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    session_id = _session_id(user_id)
    text = " ".join(context.args).strip()
    if not text:
        await update.message.reply_text("Usage: /forget <text>")
        return
    try:
        requests.post(PROFILE_FORGET_URL, json={"session_id": session_id, "text": text}, timeout=10)
        await update.message.reply_text(f"Removed: {text}")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")


async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    session_id = _session_id(user_id)
    profile = await asyncio.to_thread(_get_profile_api, session_id)
    if not profile:
        await update.message.reply_text("No profile saved yet. Run /setup to get started.")
        return
    # Remove internal fields before showing
    display = {k: v for k, v in profile.items() if k not in ("pending_confirmation", "updated_at")}
    await _send_long(update.message, json.dumps(display, ensure_ascii=False, indent=2))


async def model_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
    default_model = os.getenv("DEFAULT_MODEL", "llama3.2:3b")
    groq_model = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
    groq_key = os.getenv("GROQ_API_KEY", "")

    ollama_ok = False
    try:
        r = requests.get(f"{ollama_url}/api/tags", timeout=3)
        ollama_ok = r.status_code == 200
    except Exception:
        pass

    if ollama_ok:
        status = f"Local model active: {default_model}\nOllama is running."
    elif groq_key:
        status = f"Local Ollama is offline.\nUsing Groq cloud: {groq_model}"
    else:
        status = "No model available! Ollama is offline and GROQ_API_KEY is not set."

    await update.message.reply_text(status)


async def download_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text(
            "Usage: /download <url> [audio_only=true] [quality=best|medium|worst]\n"
            "Examples:\n"
            "  /download https://tiktok.com/...\n"
            "  /download https://instagram.com/... quality=medium\n"
            "  /download https://youtube.com/... audio_only=true"
        )
        return

    url = context.args[0].strip()
    audio_only = False
    quality = "best"
    for arg in context.args[1:]:
        k, _, v = arg.partition("=")
        if k.lower() == "audio_only":
            audio_only = v.lower() in {"1", "true", "yes"}
        elif k.lower() == "quality" and v.lower() in {"best", "medium", "worst"}:
            quality = v.lower()

    await update.message.reply_text("Downloading... this may take a moment.")
    try:
        resp = requests.post(
            DOWNLOAD_URL,
            json={"url": url, "audio_only": audio_only, "quality": quality},
            timeout=600,
        )
        result = resp.json().get("response", "Done.")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")
        return

    # Tool returns "FILE:<path>|TITLE:<name>|SIZE:<mb>|TMPDIR:<dir>" on success
    if result.startswith("FILE:"):
        import shutil as _shutil
        parts = dict(seg.split(":", 1) for seg in result.split("|") if ":" in seg)
        file_path = parts.get("FILE", "")
        title = parts.get("TITLE", "media")
        size_label = parts.get("SIZE", "")
        tmp_dir = parts.get("TMPDIR", "")
        caption = f"{title} ({size_label})" if size_label else title

        sent = False
        if file_path and Path(file_path).exists():
            try:
                with open(file_path, "rb") as f:
                    if audio_only or file_path.lower().endswith((".mp3", ".m4a", ".ogg", ".opus", ".flac")):
                        await update.message.reply_audio(audio=f, caption=caption)
                    else:
                        await update.message.reply_video(video=f, caption=caption, supports_streaming=True)
                sent = True
            except Exception:
                # Streaming failed — send as generic document (works for any file type)
                try:
                    with open(file_path, "rb") as f:
                        await update.message.reply_document(document=f, caption=caption)
                    sent = True
                except Exception as doc_err:
                    await update.message.reply_text(f"Could not send file: {doc_err}")

        # Always delete the temp dir — no permanent storage on server
        if tmp_dir:
            _shutil.rmtree(tmp_dir, ignore_errors=True)

        if not sent and not tmp_dir:
            await update.message.reply_text(result)
    else:
        await _send_long(update.message, result)


# ---------------------------------------------------------------------------
# Reminder commands
# ---------------------------------------------------------------------------

async def _reminder_fired(context: ContextTypes.DEFAULT_TYPE) -> None:
    """JobQueue callback for a reminder."""
    from interfaces.telegram.scheduler import remove_reminder
    data = context.job.data
    await context.bot.send_message(chat_id=data["chat_id"], text=f"Reminder: {data['message']}")
    remove_reminder(data.get("reminder_id", ""))


async def remind_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from interfaces.telegram.scheduler import parse_reminder_time, save_reminder

    user_id = update.effective_user.id
    text = " ".join(context.args).strip()
    if not text:
        await update.message.reply_text(
            "Usage:\n"
            "  /remind in 2 hours call mom\n"
            "  /remind in 30 minutes take a break\n"
            "  /remind at 6pm buy groceries\n"
            "  /remind at 9:30am standup\n"
            "  /remind tomorrow at 8am check emails"
        )
        return

    run_at, msg = parse_reminder_time(text)
    if run_at is None:
        await update.message.reply_text(msg)
        return

    chat_id = update.effective_chat.id
    reminder_id = save_reminder(user_id, chat_id, msg, run_at)
    delay = (run_at - datetime.now()).total_seconds()

    context.job_queue.run_once(
        _reminder_fired,
        when=delay,
        data={"chat_id": chat_id, "message": msg, "reminder_id": reminder_id},
        name=reminder_id,
    )

    time_str = run_at.strftime("%I:%M %p on %b %d")
    await update.message.reply_text(f"Reminder set for {time_str}:\n{msg}")


async def reminders_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from interfaces.telegram.scheduler import get_user_reminders

    user_id = update.effective_user.id
    pending = get_user_reminders(user_id)
    if not pending:
        await update.message.reply_text("No pending reminders.")
        return

    lines = ["Your pending reminders:"]
    for r in pending:
        run_at = datetime.fromisoformat(r["run_at"])
        lines.append(f"- {run_at.strftime('%I:%M %p %b %d')}: {r['message']}")
    await update.message.reply_text("\n".join(lines))


# ---------------------------------------------------------------------------
# Briefing command
# ---------------------------------------------------------------------------

async def briefing_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    session_id = _session_id(user_id)
    briefing_prompt = (
        "Give me a morning briefing. Check: "
        "1) How many unread emails I have, "
        "2) My calendar events for today, "
        "3) Give me a short motivational thought to start the day."
    )
    await _run_jarvis(update, briefing_prompt, session_id)


# ---------------------------------------------------------------------------
# /setup guided profile conversation
# ---------------------------------------------------------------------------

async def setup_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    context.user_data["setup_sid"] = _session_id(user_id)
    await update.message.reply_text(
        "Let's set up your Jarvis profile! I'll ask a few quick questions.\n"
        "Type your answer or type 'skip' to skip any question.\n\n"
        "What's your full name?"
    )
    return SETUP_NAME


async def _setup_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text.lower() != "skip" and text:
        _update_profile_api(context.user_data["setup_sid"], {"name": text})
        context.user_data["setup_collected_name"] = text
    await update.message.reply_text(
        "What should Jarvis call you day-to-day? (nickname, e.g. 'Q', 'boss') — or type 'skip'"
    )
    return SETUP_NICKNAME


async def _setup_nickname(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text.lower() != "skip" and text:
        _update_profile_api(context.user_data["setup_sid"], {"nickname": text})
    await update.message.reply_text("Where are you based? (city, country) — or 'skip'")
    return SETUP_LOCATION


async def _setup_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text.lower() != "skip" and text:
        _update_profile_api(context.user_data["setup_sid"], {"location": text})
    await update.message.reply_text("What do you do? (job, studies, profession) — or 'skip'")
    return SETUP_PROFESSION


async def _setup_profession(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text.lower() != "skip" and text:
        _update_profile_api(context.user_data["setup_sid"], {"profession": text})
    await update.message.reply_text("What are you currently building or working on? — or 'skip'")
    return SETUP_PROJECT


async def _setup_project(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text.lower() != "skip" and text:
        _update_profile_api(context.user_data["setup_sid"], {"current_project": text})
    await update.message.reply_text(
        "What are your main goals? (e.g. 'build a SaaS, learn AI, get fit') — or 'skip'"
    )
    return SETUP_GOALS


async def _setup_goals(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text.lower() != "skip" and text:
        goals = [g.strip() for g in text.replace(";", ",").split(",") if g.strip()]
        _update_profile_api(context.user_data["setup_sid"], {"goals": goals})
    await update.message.reply_text(
        "What are your interests or hobbies? (e.g. 'coding, music, football') — or 'skip'"
    )
    return SETUP_INTERESTS


async def _setup_interests(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text.lower() != "skip" and text:
        interests = [i.strip() for i in text.replace(";", ",").split(",") if i.strip()]
        _update_profile_api(context.user_data["setup_sid"], {"interests": interests})
    await update.message.reply_text(
        "How should Jarvis talk to you?\n"
        "1 — Casual (like a close friend)\n"
        "2 — Professional (formal)\n"
        "Type 1 or 2, or 'skip'"
    )
    return SETUP_STYLE


async def _setup_style(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    style_map = {"1": "casual", "casual": "casual", "2": "formal", "professional": "formal", "formal": "formal"}
    style = style_map.get(text.lower())
    if style:
        _update_profile_api(context.user_data["setup_sid"], {"communication_style": style})

    name = context.user_data.get("setup_collected_name", "")
    greeting = f"You're all set{', ' + name if name else ''}!"
    await update.message.reply_text(
        f"{greeting}\n\n"
        "Jarvis now knows you and will get smarter over time.\n\n"
        "You can always update your profile with /remember or /setup again."
    )
    context.user_data.pop("setup_sid", None)
    context.user_data.pop("setup_collected_name", None)
    return ConversationHandler.END


async def _setup_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Setup cancelled. Run /setup anytime to continue.")
    context.user_data.pop("setup_sid", None)
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# Message handlers
# ---------------------------------------------------------------------------

_MEDIA_DOMAINS = (
    "tiktok.com", "vm.tiktok.com", "vt.tiktok.com",
    "instagram.com", "instagr.am",
    "facebook.com", "fb.watch", "fb.com",
    "youtube.com", "youtu.be",
    "twitter.com", "x.com", "t.co",
    "reddit.com", "redd.it",
    "twitch.tv",
    "dailymotion.com",
    "vimeo.com",
)

def _extract_media_url(text: str) -> str | None:
    """Return the URL if the message is (or contains) a social media video link."""
    import re
    urls = re.findall(r"https?://\S+", text.strip())
    for url in urls:
        url = url.rstrip(".,)")
        if any(domain in url for domain in _MEDIA_DOMAINS):
            return url
    return None


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not _is_owner(user_id):
        await update.message.reply_text("Sorry, I only respond to my owner.")
        return

    session_id = _session_id(user_id)
    user_message = update.message.text
    logger.info(f"[{user_id}] text: {user_message[:60]}")

    # If the message is a social media URL, download it directly — no LLM needed
    media_url = _extract_media_url(user_message)
    if media_url:
        context.args = [media_url]
        await download_command(update, context)
        return

    await _run_jarvis(update, user_message, session_id)


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Transcribe voice note via Groq Whisper, then run through Jarvis."""
    from app.llm.groq_media import transcribe_audio

    user_id = update.effective_user.id
    if not _is_owner(user_id):
        return

    session_id = _session_id(user_id)
    await update.message.reply_text("Transcribing your voice message...")

    voice = update.message.voice
    tg_file = await context.bot.get_file(voice.file_id)

    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        await tg_file.download_to_drive(tmp_path)
        transcription = await asyncio.to_thread(transcribe_audio, tmp_path)

        if transcription.startswith("Error") or "failed" in transcription.lower():
            await update.message.reply_text(f"Could not transcribe: {transcription}")
            return

        await update.message.reply_text(f"You said: {transcription}")
        logger.info(f"[{user_id}] voice transcribed: {transcription[:60]}")
        await _run_jarvis(update, transcription, session_id)

    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Analyze photo via Groq Vision, then pass description + caption to Jarvis."""
    from app.llm.groq_media import analyze_image

    user_id = update.effective_user.id
    if not _is_owner(user_id):
        return

    session_id = _session_id(user_id)
    caption = update.message.caption or ""
    await update.message.reply_text("Analyzing image...")

    photo = update.message.photo[-1]  # largest available
    tg_file = await context.bot.get_file(photo.file_id)

    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        await tg_file.download_to_drive(tmp_path)
        vision_prompt = caption if caption else "Describe this image in detail."
        description = await asyncio.to_thread(analyze_image, tmp_path, vision_prompt)

        if description.startswith("Error"):
            await update.message.reply_text(f"Could not analyze image: {description}")
            return

        if caption:
            jarvis_msg = f"[Image with caption: '{caption}']\nImage description: {description}"
        else:
            jarvis_msg = f"[User sent an image]\nImage description: {description}\n\nWhat can you tell me about this?"

        logger.info(f"[{user_id}] photo analyzed")
        await _run_jarvis(update, jarvis_msg, session_id)

    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Extract text from document and pass to Jarvis."""
    user_id = update.effective_user.id
    if not _is_owner(user_id):
        return

    session_id = _session_id(user_id)
    doc = update.message.document
    caption = update.message.caption or ""
    file_name = doc.file_name or "document"
    ext = os.path.splitext(file_name)[1].lower()

    supported_text = {".txt", ".py", ".js", ".ts", ".md", ".json", ".csv", ".html", ".css", ".yaml", ".yml", ".xml", ".log"}
    supported_pdf = {".pdf"}
    if ext not in supported_text and ext not in supported_pdf:
        await update.message.reply_text(
            f"I can process text files ({', '.join(sorted(supported_text))}) and PDFs.\n"
            f"Got: {ext or 'unknown'}"
        )
        return

    await update.message.reply_text(f"Processing {file_name}...")
    tg_file = await context.bot.get_file(doc.file_id)

    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp_path = tmp.name

    try:
        await tg_file.download_to_drive(tmp_path)

        if ext in supported_pdf:
            text = await asyncio.to_thread(_extract_pdf, tmp_path)
        else:
            with open(tmp_path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()

        if not text or len(text.strip()) < 10:
            await update.message.reply_text("Could not extract text from this file.")
            return

        if len(text) > 8000:
            text = text[:8000] + "\n...[truncated at 8000 chars]"

        if caption:
            jarvis_msg = f"[Document: {file_name}]\n{text}\n\nUser request: {caption}"
        else:
            jarvis_msg = f"[Document received: {file_name}]\n\n{text}\n\nPlease summarize and analyze this document."

        logger.info(f"[{user_id}] document: {file_name}")
        await _run_jarvis(update, jarvis_msg, session_id)

    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


def _extract_pdf(path: str) -> str:
    try:
        import pypdf
        reader = pypdf.PdfReader(path)
        return "\n".join(page.extract_text() or "" for page in reader.pages).strip()
    except ImportError:
        return "PDF support requires pypdf. Install with: pip install pypdf"
    except Exception as e:
        return f"Could not read PDF: {e}"


# ---------------------------------------------------------------------------
# Error handler
# ---------------------------------------------------------------------------

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f"Update {update} caused error: {context.error}")
    if update and update.effective_message:
        await update.effective_message.reply_text("An error occurred. Please try again.")


# ---------------------------------------------------------------------------
# Startup: restore persisted reminders
# ---------------------------------------------------------------------------

async def post_init(application: Application) -> None:
    from interfaces.telegram.scheduler import load_reminders, purge_expired_reminders
    purge_expired_reminders()
    reminders = load_reminders()
    now = datetime.now()
    restored = 0
    for r in reminders:
        run_at = datetime.fromisoformat(r["run_at"])
        if run_at <= now:
            continue
        delay = (run_at - now).total_seconds()
        application.job_queue.run_once(
            _reminder_fired,
            when=delay,
            data={"chat_id": r["chat_id"], "message": r["message"], "reminder_id": r["id"]},
            name=r["id"],
        )
        restored += 1
    if restored:
        logger.info(f"Restored {restored} reminder(s) from storage.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def build_application():
    """Build and return the configured Application (without starting it)."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token or token == "your_telegram_bot_token_here":
        raise ValueError("TELEGRAM_BOT_TOKEN not set")

    application = Application.builder().token(token).post_init(post_init).build()

    setup_conv = ConversationHandler(
        entry_points=[CommandHandler("setup", setup_start)],
        states={
            SETUP_NAME:       [MessageHandler(filters.TEXT & ~filters.COMMAND, _setup_name)],
            SETUP_NICKNAME:   [MessageHandler(filters.TEXT & ~filters.COMMAND, _setup_nickname)],
            SETUP_LOCATION:   [MessageHandler(filters.TEXT & ~filters.COMMAND, _setup_location)],
            SETUP_PROFESSION: [MessageHandler(filters.TEXT & ~filters.COMMAND, _setup_profession)],
            SETUP_PROJECT:    [MessageHandler(filters.TEXT & ~filters.COMMAND, _setup_project)],
            SETUP_GOALS:      [MessageHandler(filters.TEXT & ~filters.COMMAND, _setup_goals)],
            SETUP_INTERESTS:  [MessageHandler(filters.TEXT & ~filters.COMMAND, _setup_interests)],
            SETUP_STYLE:      [MessageHandler(filters.TEXT & ~filters.COMMAND, _setup_style)],
        },
        fallbacks=[CommandHandler("cancel", _setup_cancel)],
    )
    application.add_handler(setup_conv)

    application.add_handler(CommandHandler("start",     start_command))
    application.add_handler(CommandHandler("help",      help_command))
    application.add_handler(CommandHandler("clear",     clear_command))
    application.add_handler(CommandHandler("whoami",    whoami_command))
    application.add_handler(CommandHandler("remember",  remember_command))
    application.add_handler(CommandHandler("forget",    forget_command))
    application.add_handler(CommandHandler("profile",   profile_command))
    application.add_handler(CommandHandler("model",     model_command))
    application.add_handler(CommandHandler("download",  download_command))
    application.add_handler(CommandHandler("remind",    remind_command))
    application.add_handler(CommandHandler("reminders", reminders_command))
    application.add_handler(CommandHandler("briefing",  briefing_command))

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(filters.VOICE,        handle_voice))
    application.add_handler(MessageHandler(filters.PHOTO,        handle_photo))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    application.add_error_handler(error_handler)
    return application


def main() -> None:
    """Entry point when running the bot standalone (development)."""
    logger.info("Jarvis Telegram Bot starting...")
    build_application().run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
