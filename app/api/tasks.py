"""API endpoints for background task management."""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
import logging

from app.utils.task_queue import task_queue
from app.agents.planning import Plan, run_planned_task

logger = logging.getLogger(__name__)
router = APIRouter()

task_queue.register_handler("planned_agent", run_planned_task)


class TaskSubmitRequest(BaseModel):
    task_type: str
    params: dict = {}
    session_id: str = "local"


class TaskResponse(BaseModel):
    task_id: str
    status: str
    message: str


@router.post("/tasks/submit")
async def submit_task(req: TaskSubmitRequest):
    """Submit a new background task."""
    # Add session_id to params
    params = {**req.params, "session_id": req.session_id}
    
    task_id = await task_queue.submit(req.task_type, params)
    
    return TaskResponse(
        task_id=task_id,
        status="pending",
        message=f"Task submitted. Check status at /tasks/{task_id}/status"
    )


@router.get("/tasks/{task_id}/status")
async def get_task_status(task_id: str):
    """Get the status of a background task."""
    status = await task_queue.get_status(task_id)
    
    if not status:
        return {"error": "Task not found"}

    if status.get("task_type") == "planned_agent":
        plan = Plan.load(task_id)
        if plan:
            status["plan"] = plan.to_dict()
            status["progress"] = plan.progress()
            status["steps"] = plan.to_dict().get("steps", [])
    
    return status


@router.get("/tasks/list")
async def list_tasks(session_id: str = "local"):
    """List all tasks for a session."""
    tasks = await task_queue.list_tasks(session_id)
    return {"tasks": tasks}


@router.get("/tasks/cleanup")
async def cleanup_tasks(max_age_hours: int = 24):
    """Clean up old completed/failed tasks."""
    await task_queue.cleanup_old_tasks(max_age_hours)
    return {"message": f"Cleaned up tasks older than {max_age_hours} hours"}
