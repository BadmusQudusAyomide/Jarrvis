"""Async versions of tools for non-blocking execution."""
import asyncio
import logging
from app.tools.system_tools import TOOLS, execute_tool as sync_execute_tool

logger = logging.getLogger(__name__)


async def execute_tool_async(tool_name: str, args: dict = None) -> str:
    """Execute a tool asynchronously using thread pool.
    
    This prevents blocking the event loop when tools take time (e.g., psutil calls).
    """
    args = args or {}
    
    try:
        # Run the blocking tool execution in a thread pool
        result = await asyncio.to_thread(sync_execute_tool, tool_name, args)
        logger.info(f"Async tool {tool_name} completed")
        return result
    except Exception as e:
        logger.error(f"Async tool {tool_name} failed: {str(e)}")
        return f"Error executing tool '{tool_name}': {str(e)}"


async def execute_multiple_tools_async(tool_calls: list) -> list:
    """Execute multiple tools concurrently.
    
    Args:
        tool_calls: List of dicts with 'tool' and 'args' keys
        
    Returns:
        List of results in same order as tool_calls
    """
    tasks = [
        execute_tool_async(call['tool'], call.get('args', {}))
        for call in tool_calls
    ]
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Convert exceptions to error strings
    processed_results = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(f"Tool {tool_calls[i]['tool']} raised exception: {str(result)}")
            processed_results.append(f"Error: {str(result)}")
        else:
            processed_results.append(result)
    
    return processed_results
