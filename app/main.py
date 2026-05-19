import asyncio
import sys
import threading
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
import os
from app.utils.logging_config import setup_logging
from app.api.chat import router as chat_router
from app.api.tasks import router as tasks_router
from app.api.system import router as system_router

# Windows async event loop policy for Playwright
if sys.platform == "windows":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Initialize structured logging
setup_logging()
logger = logging.getLogger(__name__)


def _start_telegram_bot() -> None:
    """Run the Telegram bot in a background daemon thread (has its own event loop)."""
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token or token == "your_telegram_bot_token_here":
        logger.warning("TELEGRAM_BOT_TOKEN not set — Telegram bot will not start.")
        return
    try:
        from interfaces.telegram.bot import main as bot_main
        logger.info("Starting Telegram bot...")
        bot_main()
    except Exception as e:
        logger.error(f"Telegram bot crashed: {e}", exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start the Telegram bot in a daemon thread so it runs alongside FastAPI
    bot_thread = threading.Thread(target=_start_telegram_bot, daemon=True, name="telegram-bot")
    bot_thread.start()
    yield
    # Daemon thread stops automatically when the main process exits


app = FastAPI(title="Jarvis AI", lifespan=lifespan)

# Add CORS middleware to allow frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers
app.include_router(chat_router)
app.include_router(tasks_router)
app.include_router(system_router)

# Check if frontend build exists
frontend_build_path = os.path.join(os.path.dirname(__file__), "..", "static", "frontend")
if os.path.exists(frontend_build_path):
    # Serve static files
    app.mount("/static", StaticFiles(directory=frontend_build_path), name="static")
    
    @app.get("/")
    async def serve_frontend():
        return FileResponse(os.path.join(frontend_build_path, "index.html"))
    
    @app.get("/{path:path}")
    async def serve_frontend_routes(path: str):
        # Serve index.html for all routes (SPA behavior)
        file_path = os.path.join(frontend_build_path, path)
        if os.path.exists(file_path) and os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(frontend_build_path, "index.html"))
else:
    @app.get("/")
    def root():
        return {"message": "Jarvis API is running. Frontend not built yet. Run 'cd frontend && npm run build' to build the React app."}
