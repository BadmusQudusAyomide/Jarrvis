"""Background task queue for long-running operations."""
import asyncio
import uuid
import logging
from datetime import datetime
from typing import Dict, Callable, Any, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class BackgroundTask:
    """Represents a background task."""
    
    def __init__(self, task_id: str, task_type: str, params: dict):
        self.task_id = task_id
        self.task_type = task_type
        self.params = params
        self.status = TaskStatus.PENDING
        self.result = None
        self.error = None
        self.created_at = datetime.now()
        self.started_at = None
        self.completed_at = None
    
    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "status": self.status.value,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None
        }


class TaskQueue:
    """Simple in-memory background task queue."""
    
    def __init__(self):
        self.tasks: Dict[str, BackgroundTask] = {}
        self._handlers: Dict[str, Callable] = {}
        self._lock = asyncio.Lock()
    
    def register_handler(self, task_type: str, handler: Callable):
        """Register a handler function for a task type."""
        self._handlers[task_type] = handler
        logger.info(f"Registered handler for task type: {task_type}")
    
    async def submit(self, task_type: str, params: dict = None) -> str:
        """Submit a new background task."""
        task_id = str(uuid.uuid4())[:8]
        task = BackgroundTask(task_id, task_type, params or {})
        
        async with self._lock:
            self.tasks[task_id] = task
        
        logger.info(f"Submitted task {task_id} of type {task_type}")
        
        # Start the task immediately
        asyncio.create_task(self._run_task(task_id))
        
        return task_id
    
    async def _run_task(self, task_id: str):
        """Execute a task and update its status."""
        task = self.tasks.get(task_id)
        if not task:
            return
        
        handler = self._handlers.get(task.task_type)
        if not handler:
            task.status = TaskStatus.FAILED
            task.error = f"No handler registered for task type: {task.task_type}"
            logger.error(task.error)
            return
        
        task.status = TaskStatus.RUNNING
        task.started_at = datetime.now()
        logger.info(f"Starting task {task_id}")
        
        try:
            # Run the handler
            if asyncio.iscoroutinefunction(handler):
                result = await handler(**task.params)
            else:
                result = await asyncio.to_thread(handler, **task.params)
            
            task.result = result
            task.status = TaskStatus.COMPLETED
            logger.info(f"Task {task_id} completed successfully")
            
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = str(e)
            logger.error(f"Task {task_id} failed: {str(e)}")
        
        task.completed_at = datetime.now()
    
    async def get_status(self, task_id: str) -> Optional[dict]:
        """Get the status of a task."""
        task = self.tasks.get(task_id)
        if task:
            return task.to_dict()
        return None
    
    async def list_tasks(self, session_id: str = None) -> list:
        """List all tasks, optionally filtered by session."""
        tasks = list(self.tasks.values())
        
        if session_id:
            tasks = [t for t in tasks if t.params.get("session_id") == session_id]
        
        # Sort by creation time, newest first
        tasks.sort(key=lambda t: t.created_at, reverse=True)
        
        return [t.to_dict() for t in tasks]
    
    async def cleanup_old_tasks(self, max_age_hours: int = 24):
        """Remove completed/failed tasks older than specified hours."""
        cutoff = datetime.now() - __import__('datetime').timedelta(hours=max_age_hours)
        
        async with self._lock:
            to_remove = [
                task_id for task_id, task in self.tasks.items()
                if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED)
                and task.created_at < cutoff
            ]
            for task_id in to_remove:
                del self.tasks[task_id]
            
            if to_remove:
                logger.info(f"Cleaned up {len(to_remove)} old tasks")


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
