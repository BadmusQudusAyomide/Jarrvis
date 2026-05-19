"""Terminal/command execution tool with safety restrictions."""
import subprocess
import os
import logging
from pathlib import Path
from app.tools.base import BaseTool, ToolSchema, ToolParameter

logger = logging.getLogger(__name__)

# Dangerous commands that are NEVER allowed (first word only)
DANGEROUS_COMMANDS = {
    'del', 'format', 'fdisk', 'diskpart', 'shutdown', 'reboot', 'halt',
    'rm', 'sudo', 'su', 'passwd', 'chmod', 'chown', 'fdisk', 'mkfs',
    'net', 'reg', 'wscript', 'cscript', 'rundll32', 'powershell', 'cmd',
    'taskkill', 'sc', 'icacls', 'attrib', 'cipher'
}

# Command injection characters to block
INJECTION_CHARS = ['&&', '||', ';', '|', '`', '$(', '${']

# Execution limits
TIMEOUT_SECONDS = 30
MAX_OUTPUT_CHARS = 5000
MAX_OUTPUT_LINES = 100


class ExecuteCommandTool(BaseTool):
    """Execute terminal commands safely with restrictions."""
    
    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="execute_command",
            description="Execute a terminal command safely. Commands run from workspace directory with 30s timeout and output limits. Dangerous commands and command chaining are blocked.",
            parameters=[
                ToolParameter(
                    name="command",
                    type="string",
                    description="Command to execute (e.g., 'dir', 'ping google.com', 'python script.py'). No command chaining with &&, ||, ; allowed.",
                    required=True
                ),
                ToolParameter(
                    name="working_dir",
                    type="string",
                    description="Working directory for command (default: workspace root). Use relative path like 'folder/subfolder'.",
                    required=False
                )
            ],
            return_type="string"
        )
    
    def execute(self, command: str, working_dir: str = ".", **kwargs) -> str:
        try:
            # Basic validation
            if not command or not command.strip():
                return "Error: Empty command"
            
            command = command.strip()
            logger.info(f"Executing command: {command}")
            
            # Check for command injection
            for char in INJECTION_CHARS:
                if char in command:
                    return f"Error: Command chaining character '{char}' not allowed for security"
            
            # Get first token and check dangerous commands
            tokens = command.split()
            if tokens:
                first_token = tokens[0].lower()
                # Remove .exe extension if present
                if first_token.endswith('.exe'):
                    first_token = first_token[:-4]
                
                if first_token in DANGEROUS_COMMANDS:
                    return f"Error: Command '{tokens[0]}' is not allowed for security"
            
            # Set working directory
            workspace_dir = Path(os.getenv("JARVIS_WORKSPACE", r"C:\Users\HP\Documents\Jarvis")).resolve()
            
            # Ensure workspace exists
            workspace_dir.mkdir(parents=True, exist_ok=True)
            
            if working_dir and working_dir != ".":
                work_path = workspace_dir / working_dir
                if not work_path.exists():
                    return f"Error: Working directory '{working_dir}' does not exist"
                if not work_path.is_dir():
                    return f"Error: '{working_dir}' is not a directory"
                cwd = str(work_path)
            else:
                cwd = str(workspace_dir)
            
            # Execute command
            try:
                # Use shell=True for Windows commands like dir, ping, ipconfig
                # But be more restrictive for other platforms
                result = subprocess.run(
                    command,
                    shell=True,
                    cwd=cwd,
                    capture_output=True,
                    text=True,
                    timeout=TIMEOUT_SECONDS,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                )
                
                # Get output
                stdout = result.stdout or ""
                stderr = result.stderr or ""
                
                # Apply output limits
                output_lines = []
                if stdout:
                    stdout_lines = stdout.splitlines()
                    if len(stdout_lines) > MAX_OUTPUT_LINES:
                        stdout_lines = stdout_lines[:MAX_OUTPUT_LINES]
                        stdout_lines.append(f"... (output truncated, showing first {MAX_OUTPUT_LINES} lines)")
                    stdout = "\n".join(stdout_lines)
                
                if len(stdout) > MAX_OUTPUT_CHARS:
                    stdout = stdout[:MAX_OUTPUT_CHARS] + f"\n... (output truncated at {MAX_OUTPUT_CHARS} characters)"
                
                # Prepare response
                response_parts = []
                
                if stdout.strip():
                    response_parts.append(stdout)
                
                if stderr.strip():
                    if stderr.lower().startswith('error:') or result.returncode != 0:
                        response_parts.append(f"Error: {stderr}")
                    else:
                        response_parts.append(f"Warning: {stderr}")
                
                if result.returncode != 0 and not stderr.strip():
                    response_parts.append(f"Command failed with exit code {result.returncode}")
                
                # Add execution info
                if response_parts:
                    final_output = "\n".join(response_parts)
                else:
                    final_output = "Command executed successfully (no output)"
                
                # Add metadata
                final_output += f"\n\n[Exit code: {result.returncode}, Timeout: {TIMEOUT_SECONDS}s, Working dir: {cwd}]"
                
                logger.info(f"Command completed: exit_code={result.returncode}, output_len={len(final_output)}")
                return final_output
                
            except subprocess.TimeoutExpired:
                return f"Error: Command timed out after {TIMEOUT_SECONDS} seconds"
            except FileNotFoundError:
                return f"Error: Command not found - '{tokens[0]}' is not recognized"
            except PermissionError:
                return "Error: Permission denied - command requires elevated privileges"
            except Exception as e:
                logger.error(f"Command execution failed: {str(e)}", exc_info=True)
                return f"Error executing command: {str(e)}"
                
        except Exception as e:
            logger.error(f"Terminal tool failed: {str(e)}", exc_info=True)
            return f"Error: {str(e)}"
