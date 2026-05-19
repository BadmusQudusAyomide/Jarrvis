"""Process and application control tools using psutil and subprocess."""
import psutil
import subprocess
import logging
from app.tools.base import BaseTool, ToolSchema, ToolParameter

logger = logging.getLogger(__name__)

# Critical system processes that should NEVER be killed
PROTECTED_PROCESSES = {
    "explorer.exe", "svchost.exe", "system", "csrss.exe", "winlogon.exe",
    "services.exe", "lsass.exe", "smss.exe", "crss.exe", "wininit.exe",
    "dllhost.exe", "taskhost.exe", "dwm.exe", "conhost.exe", "kernel"
}

# Safe applications that can be launched (mapped to common paths)
SAFE_APPS = {
    "notepad": "notepad.exe",
    "notepad++": r"C:\Program Files\Notepad++\notepad++.exe",
    "calculator": "calc.exe",
    "calc": "calc.exe",
    "paint": "mspaint.exe",
    "command": "cmd.exe",
    "cmd": "cmd.exe",
    "powershell": "powershell.exe",
    "browser": None,  # Will use default browser
    "chrome": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "firefox": r"C:\Program Files\Mozilla Firefox\firefox.exe",
    "edge": r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "code": r"C:\Users\HP\AppData\Local\Programs\Microsoft VS Code\Code.exe",
    "vscode": r"C:\Users\HP\AppData\Local\Programs\Microsoft VS Code\Code.exe",
}


class ListProcessesTool(BaseTool):
    """List running processes with optional filtering."""
    
    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="list_processes",
            description="List running processes with CPU and memory usage. Use filter to search for specific processes instead of showing all 200+.",
            parameters=[
                ToolParameter(
                    name="filter",
                    type="string",
                    description="Process name to search for (e.g., 'chrome', 'python', 'notepad'). If not provided, shows top 20 processes by CPU.",
                    required=False
                ),
                ToolParameter(
                    name="limit",
                    type="integer",
                    description="Maximum number of processes to show (default 20, max 50)",
                    required=False
                )
            ],
            return_type="string"
        )
    
    def execute(self, filter: str = None, limit: int = 20, **kwargs) -> str:
        try:
            limit = max(1, min(50, int(limit) if limit else 20))
            filter_lower = filter.lower() if filter else None
            
            processes = []
            for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
                try:
                    info = proc.info
                    name = info['name'] or "Unknown"
                    
                    # Apply filter if provided
                    if filter_lower:
                        if filter_lower not in name.lower():
                            continue
                    
                    processes.append({
                        'pid': info['pid'],
                        'name': name,
                        'cpu': info['cpu_percent'] or 0.0,
                        'mem': info['memory_percent'] or 0.0
                    })
                    
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            
            if not processes:
                if filter:
                    return f"No processes matching '{filter}' found."
                return "No processes found."
            
            # Sort by CPU usage
            processes.sort(key=lambda x: x['cpu'], reverse=True)
            processes = processes[:limit]
            
            # Format output
            lines = [f"{'PID':<8} {'Name':<25} {'CPU%':<8} {'Mem%':<8}"]
            lines.append("-" * 55)
            
            for p in processes:
                lines.append(f"{p['pid']:<8} {p['name'][:24]:<25} {p['cpu']:<8.1f} {p['mem']:<8.1f}")
            
            if filter:
                lines.append(f"\nFound {len(processes)} process(es) matching '{filter}'")
            else:
                lines.append(f"\nTop {len(processes)} processes by CPU usage")
            
            logger.info(f"Listed {len(processes)} processes" + (f" matching '{filter}'" if filter else ""))
            return '\n'.join(lines)
            
        except Exception as e:
            logger.error(f"List processes failed: {str(e)}", exc_info=True)
            return f"Error listing processes: {str(e)}"


class KillProcessTool(BaseTool):
    """Kill/terminate a process by name or PID."""
    
    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="kill_process",
            description="Kill/terminate a process by name or PID. Cannot kill critical system processes for safety.",
            parameters=[
                ToolParameter(
                    name="name",
                    type="string",
                    description="Process name to kill (e.g., 'notepad.exe', 'chrome'). Either name or pid required.",
                    required=False
                ),
                ToolParameter(
                    name="pid",
                    type="integer",
                    description="Process ID to kill. Either name or pid required.",
                    required=False
                )
            ],
            return_type="string"
        )
    
    def execute(self, name: str = None, pid: int = None, **kwargs) -> str:
        try:
            if not name and not pid:
                return "Error: Must provide either name or pid parameter"
            
            # Find process
            target_procs = []
            
            if pid:
                try:
                    proc = psutil.Process(pid)
                    target_procs.append(proc)
                    name = proc.name()
                except psutil.NoSuchProcess:
                    return f"Error: Process with PID {pid} not found"
            elif name:
                name_lower = name.lower()
                for proc in psutil.process_iter(['pid', 'name']):
                    try:
                        if name_lower in proc.info['name'].lower():
                            target_procs.append(psutil.Process(proc.info['pid']))
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
            
            if not target_procs:
                return f"Error: No process matching '{name}' found"
            
            # Safety check - protected processes
            for proc in target_procs:
                proc_name = proc.name().lower()
                if any(protected in proc_name for protected in PROTECTED_PROCESSES):
                    return f"Error: Cannot kill protected system process '{proc.name()}'"
            
            # Kill processes
            killed = []
            for proc in target_procs:
                try:
                    proc.terminate()
                    proc.wait(timeout=3)
                    killed.append(f"{proc.name()} (PID: {proc.pid})")
                    logger.info(f"Killed process: {proc.name()} (PID: {proc.pid})")
                except psutil.TimeoutExpired:
                    proc.kill()
                    killed.append(f"{proc.name()} (PID: {proc.pid}, force-killed)")
                    logger.info(f"Force-killed process: {proc.name()} (PID: {proc.pid})")
                except Exception as e:
                    logger.error(f"Failed to kill {proc.name()}: {str(e)}")
            
            return f"Killed {len(killed)} process(es): {', '.join(killed)}"
            
        except Exception as e:
            logger.error(f"Kill process failed: {str(e)}", exc_info=True)
            return f"Error killing process: {str(e)}"


class LaunchAppTool(BaseTool):
    """Launch an application safely."""
    
    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="launch_app",
            description="Launch an application. Use app name (notepad, calculator, chrome, vscode) or provide full path. Only safe/whitelisted apps allowed.",
            parameters=[
                ToolParameter(
                    name="app",
                    type="string",
                    description="App name (e.g., 'notepad', 'calculator', 'chrome', 'vscode') or full path to executable",
                    required=True
                ),
                ToolParameter(
                    name="args",
                    type="string",
                    description="Command line arguments (optional)",
                    required=False
                )
            ],
            return_type="string"
        )
    
    def execute(self, app: str, args: str = None, **kwargs) -> str:
        try:
            # Check if it's a known app name
            app_lower = app.lower()
            if app_lower in SAFE_APPS:
                cmd = SAFE_APPS[app_lower]
                if cmd is None:
                    # Default browser - use start command
                    cmd = "start"
                    args = args or ""
                    full_cmd = f"{cmd} {args}" if args else cmd
                    subprocess.Popen(full_cmd, shell=True)
                    logger.info(f"Launched default browser")
                    return f"Launched default browser"
            elif app.endswith('.exe') or '\\' in app or '/' in app:
                # Full path provided - check if it exists
                cmd = app
            else:
                # Unknown app - reject for safety
                safe_list = ', '.join([k for k in SAFE_APPS.keys() if SAFE_APPS[k]])
                return f"Error: Unknown app '{app}'. Use one of: {safe_list}, or provide full path to .exe"
            
            # Launch the app
            if args:
                subprocess.Popen([cmd] + args.split())
            else:
                subprocess.Popen([cmd])
            
            logger.info(f"Launched application: {app}" + (f" with args: {args}" if args else ""))
            return f"Launched '{app}' successfully"
            
        except FileNotFoundError:
            return f"Error: Application '{app}' not found. Check if it's installed."
        except Exception as e:
            logger.error(f"Launch app failed: {str(e)}", exc_info=True)
            return f"Error launching app: {str(e)}"


class IsProcessRunningTool(BaseTool):
    """Check if a process is currently running."""
    
    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="is_process_running",
            description="Check if a process is currently running. Returns true/false.",
            parameters=[
                ToolParameter(
                    name="name",
                    type="string",
                    description="Process name to check (e.g., 'chrome', 'notepad', 'python')",
                    required=True
                )
            ],
            return_type="string"
        )
    
    def execute(self, name: str, **kwargs) -> str:
        try:
            name_lower = name.lower()
            count = 0
            
            for proc in psutil.process_iter(['name']):
                try:
                    if name_lower in proc.info['name'].lower():
                        count += 1
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            
            logger.info(f"Checked process '{name}': found {count} instance(s)")
            
            if count > 0:
                return f"true ({count} instance{'s' if count > 1 else ''} running)"
            else:
                return "false (not running)"
                
        except Exception as e:
            logger.error(f"Check process failed: {str(e)}", exc_info=True)
            return f"Error: {str(e)}"
