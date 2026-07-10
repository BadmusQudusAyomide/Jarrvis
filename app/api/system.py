"""System monitoring endpoints."""
from fastapi import APIRouter
import psutil

from app.config import DEFAULT_MODEL

router = APIRouter()


@router.get("/system/stats")
async def system_stats():
    """Get current system resource usage."""
    cpu = psutil.cpu_percent(interval=0.1)
    ram = psutil.virtual_memory()
    return {
        "cpu_usage": f"{cpu}",
        "ram_usage": f"{ram.percent}",
        "model": DEFAULT_MODEL,
    }
