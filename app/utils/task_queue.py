"""Background task queue for long-running operations.

Backed by SQLite (data/tasks.db) instead of an in-memory dict — a server
restart used to silently erase every running or completed task; now task
metadata survives restarts. The actual handler coroutine still can't survive
a restart (there's no in-process work to resume), so any task still marked
"running" at startup is treated as interrupted and marked failed.
"""
import asyncio
import json
import sqlite3
import uuid
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)

DB_PATH = Path("data/tasks.db")


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db():
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY,
                task_type TEXT NOT NULL,
                session_id TEXT,
                params TEXT NOT NULL,
                status TEXT NOT NULL,
                result TEXT,
                error TEXT,
                created_at TEXT NOT NULL,
                started_at TEXT,
                completed_at TEXT
            )
        """)
        # Any task still "running" when the process last stopped was
        # interrupted mid-flight — its coroutine is gone, it will never finish.
        conn.execute(
            "UPDATE tasks SET status = 'failed', error = 'Interrupted by server restart', "
            "completed_at = ? WHERE status = 'running'",
            (datetime.now().isoformat(),),
        )
        conn.commit()


def _row_to_dict(row: sqlite3.Row) -> dict:
    return {
        "task_id": row["task_id"],
        "task_type": row["task_type"],
        "status": row["status"],
        "result": json.loads(row["result"]) if row["result"] else None,
        "error": row["error"],
        "created_at": row["created_at"],
        "started_at": row["started_at"],
        "completed_at": row["completed_at"],
    }


class TaskQueue:
    """SQLite-backed background task queue."""

    def __init__(self):
        _init_db()
        self._handlers: dict[str, Callable] = {}
        self._lock = asyncio.Lock()

    def register_handler(self, task_type: str, handler: Callable):
        """Register a handler function for a task type."""
        self._handlers[task_type] = handler
        logger.info(f"Registered handler for task type: {task_type}")

    async def submit(self, task_type: str, params: dict = None) -> str:
        """Submit a new background task."""
        task_id = str(uuid.uuid4())[:8]
        task_params = dict(params or {})
        task_params.setdefault("task_id", task_id)
        session_id = task_params.get("session_id")
        now = datetime.now().isoformat()

        async with self._lock:
            await asyncio.to_thread(self._insert_task, task_id, task_type, session_id, task_params, now)

        logger.info(f"Submitted task {task_id} of type {task_type}")

        # Start the task immediately
        asyncio.create_task(self._run_task(task_id, task_type, task_params))

        return task_id

    def _insert_task(self, task_id: str, task_type: str, session_id: Optional[str], params: dict, created_at: str):
        with _connect() as conn:
            conn.execute(
                "INSERT INTO tasks (task_id, task_type, session_id, params, status, created_at) "
                "VALUES (?, ?, ?, ?, 'pending', ?)",
                (task_id, task_type, session_id, json.dumps(params), created_at),
            )
            conn.commit()

    def _update_task(self, task_id: str, **fields):
        if not fields:
            return
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [task_id]
        with _connect() as conn:
            conn.execute(f"UPDATE tasks SET {set_clause} WHERE task_id = ?", values)
            conn.commit()

    async def _run_task(self, task_id: str, task_type: str, params: dict):
        """Execute a task and update its status."""
        handler = self._handlers.get(task_type)
        if not handler:
            error = f"No handler registered for task type: {task_type}"
            logger.error(error)
            await asyncio.to_thread(self._update_task, task_id, status="failed", error=error,
                                     completed_at=datetime.now().isoformat())
            return

        await asyncio.to_thread(self._update_task, task_id, status="running",
                                 started_at=datetime.now().isoformat())
        logger.info(f"Starting task {task_id}")

        try:
            if asyncio.iscoroutinefunction(handler):
                result = await handler(**params)
            else:
                result = await asyncio.to_thread(handler, **params)

            await asyncio.to_thread(
                self._update_task, task_id, status="completed",
                result=json.dumps(result), completed_at=datetime.now().isoformat(),
            )
            logger.info(f"Task {task_id} completed successfully")

        except Exception as e:
            logger.error(f"Task {task_id} failed: {str(e)}")
            await asyncio.to_thread(
                self._update_task, task_id, status="failed",
                error=str(e), completed_at=datetime.now().isoformat(),
            )

    async def get_status(self, task_id: str) -> Optional[dict]:
        """Get the status of a task."""
        return await asyncio.to_thread(self._get_status_sync, task_id)

    def _get_status_sync(self, task_id: str) -> Optional[dict]:
        with _connect() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
            return _row_to_dict(row) if row else None

    async def list_tasks(self, session_id: str = None) -> list:
        """List all tasks, optionally filtered by session."""
        return await asyncio.to_thread(self._list_tasks_sync, session_id)

    def _list_tasks_sync(self, session_id: Optional[str]) -> list:
        with _connect() as conn:
            if session_id:
                rows = conn.execute(
                    "SELECT * FROM tasks WHERE session_id = ? ORDER BY created_at DESC", (session_id,)
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM tasks ORDER BY created_at DESC").fetchall()
            return [_row_to_dict(row) for row in rows]

    async def cleanup_old_tasks(self, max_age_hours: int = 24):
        """Remove completed/failed tasks older than specified hours."""
        cutoff = (datetime.now() - timedelta(hours=max_age_hours)).isoformat()
        removed = await asyncio.to_thread(self._cleanup_sync, cutoff)
        if removed:
            logger.info(f"Cleaned up {removed} old tasks")

    def _cleanup_sync(self, cutoff: str) -> int:
        with _connect() as conn:
            cur = conn.execute(
                "DELETE FROM tasks WHERE status IN ('completed', 'failed') AND created_at < ?",
                (cutoff,),
            )
            conn.commit()
            return cur.rowcount


# Global task queue instance
task_queue = TaskQueue()


# Example task handlers
def example_long_task(duration: int = 5, **kwargs):
    """Example handler that simulates a long-running task."""
    import time
    time.sleep(duration)
    return f"Task completed after {duration} seconds"


# Register example handler
task_queue.register_handler("example", example_long_task)
