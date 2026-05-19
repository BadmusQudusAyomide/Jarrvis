"""Code execution tools with sandbox security."""
import logging
import subprocess
import os
import re
from datetime import datetime
from pathlib import Path
from app.tools.base import BaseTool, ToolSchema, ToolParameter

logger = logging.getLogger(__name__)

# Define blocked modules for security
BLOCKED_MODULES = {
    'os', 'subprocess', 'socket', 'sys', 'shutil',
    'pathlib', 'glob', 'importlib', 'ctypes', 'winreg'
}

# Workspace and sandbox directories
WORKSPACE_DIR = Path(r'C:\Users\HP\Documents\Jarvis\workspace')
SANDBOX_DIR = WORKSPACE_DIR / '.sandbox'


def ensure_sandbox_dir():
    """Ensure the sandbox directory exists."""
    SANDBOX_DIR.mkdir(parents=True, exist_ok=True)
    return SANDBOX_DIR


def check_import_security(code: str) -> tuple[bool, str]:
    """Check if code contains blocked imports.
    
    Returns:
        (is_safe, error_message)
    """
    for module in BLOCKED_MODULES:
        # Check for 'import module' or 'from module' patterns
        import_pattern = rf'^\s*import\s+{module}\b'
        from_pattern = rf'^\s*from\s+{module}\b'
        
        if re.search(import_pattern, code, re.MULTILINE) or re.search(from_pattern, code, re.MULTILINE):
            return False, f"Error: Module '{module}' is not allowed for security reasons"
    
    return True, ""


class ExecuteCodeTool(BaseTool):
    """Execute Python code in a secure sandbox environment."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="execute_code",
            description="Execute Python code in a secure sandbox. Code runs in isolated subprocess with security restrictions. Blocked modules: os, subprocess, socket, sys, shutil, pathlib, glob, importlib, ctypes, winreg.",
            parameters=[
                ToolParameter(
                    name="code",
                    type="string",
                    description="Python code string to execute",
                    required=True
                ),
                ToolParameter(
                    name="timeout",
                    type="integer",
                    description="Execution timeout in seconds (default: 10, max: 30)",
                    required=False
                )
            ],
            return_type="string"
        )

    def execute(self, code: str, timeout: int = 10, **kwargs) -> str:
        try:
            # Validate timeout
            timeout = min(max(int(timeout), 1), 30)  # Clamp between 1-30 seconds
            
            # Security check - block dangerous imports
            is_safe, error_msg = check_import_security(code)
            if not is_safe:
                logger.warning(f"Blocked code execution: {error_msg}")
                return error_msg
            
            # Ensure sandbox directory exists
            sandbox = ensure_sandbox_dir()
            
            # Create temp file with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            temp_file = sandbox / f"temp_{timestamp}.py"
            
            # Write code to temp file
            temp_file.write_text(code, encoding='utf-8')
            logger.info(f"Code written to sandbox: {temp_file}")
            
            try:
                # Execute code in subprocess
                result = subprocess.run(
                    ['python', str(temp_file)],
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    cwd=str(WORKSPACE_DIR)
                )
                
                # Build output
                output_parts = []
                
                if result.stdout:
                    output_parts.append(f"Output:\n{result.stdout}")
                
                if result.stderr:
                    output_parts.append(f"Errors:\n{result.stderr}")
                
                if result.returncode != 0:
                    output_parts.append(f"Exit code: {result.returncode}")
                
                if not output_parts:
                    output = "Code executed successfully (no output)"
                else:
                    output = "\n".join(output_parts)
                
                logger.info(f"Code executed with return code: {result.returncode}")
                return output
                
            except subprocess.TimeoutExpired:
                logger.warning(f"Code execution timed out after {timeout} seconds")
                return f"Error: Code execution timed out after {timeout} seconds"
            
            except Exception as e:
                logger.error(f"Error executing code: {str(e)}", exc_info=True)
                return f"Error executing code: {str(e)}"
            
            finally:
                # Clean up temp file
                try:
                    temp_file.unlink()
                    logger.info(f"Cleaned up sandbox file: {temp_file}")
                except Exception as e:
                    logger.warning(f"Failed to clean up temp file: {e}")
        
        except Exception as e:
            logger.error(f"Failed to execute code: {str(e)}", exc_info=True)
            return f"Error executing code: {str(e)}"
