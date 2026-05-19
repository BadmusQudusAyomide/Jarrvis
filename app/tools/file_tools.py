"""File system tools for reading, writing, and managing files safely."""
import os
import logging
from pathlib import Path
from typing import Optional, List
from app.tools.base import BaseTool, ToolSchema, ToolParameter

logger = logging.getLogger(__name__)

# Base directory for all file operations (sandbox)
WORKSPACE_DIR = Path(os.getenv("JARVIS_WORKSPACE", r"C:\Users\HP\Documents\Jarvis")).resolve()

# Recycle bin within workspace
RECYCLE_DIR = WORKSPACE_DIR / ".recycle"
RECYCLE_DIR.mkdir(parents=True, exist_ok=True)


def _ensure_safe_path(path: str) -> Path:
    """Ensure path is within workspace directory. Raises if outside."""
    # Handle relative paths
    if not path.startswith('/') and not path.startswith('\\'):
        full_path = (WORKSPACE_DIR / path).resolve()
    else:
        # Absolute path - check if it's within workspace
        full_path = Path(path).resolve()
    
    # Security check - must be within workspace
    try:
        full_path.relative_to(WORKSPACE_DIR)
    except ValueError:
        raise ValueError(f"Path {path} is outside the workspace directory {WORKSPACE_DIR}")
    
    return full_path


class ReadFileTool(BaseTool):
    """Tool to read file contents."""
    
    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="read_file",
            description="Read the contents of a text file. Use for reading configs, logs, code, or any text file. Limited to workspace directory for security.",
            parameters=[
                ToolParameter(
                    name="path",
                    type="string",
                    description="Path to the file (use relative path like 'test.txt' or 'folder/file.txt', NOT absolute paths like '/home/...')",
                    required=True
                ),
                ToolParameter(
                    name="limit",
                    type="integer",
                    description="Max lines to read (default 100, max 500)",
                    required=False
                )
            ],
            return_type="string"
        )
    
    def execute(self, path: str, limit: int = 100, **kwargs) -> str:
        try:
            file_path = _ensure_safe_path(path)
            
            if not file_path.exists():
                return f"Error: File '{path}' not found"
            
            if not file_path.is_file():
                return f"Error: '{path}' is not a file"
            
            # Clamp limit
            limit = max(1, min(500, int(limit)))
            
            logger.info(f"Reading file: {file_path} (limit={limit} lines)")
            
            # Read file
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    lines = []
                    line_count = 0
                    for i, line in enumerate(f):
                        if i >= limit:
                            line_count = i + 1
                            break
                        lines.append(line.rstrip())
                        line_count = i + 1
                    
                    content = '\n'.join(lines)
                    if line_count >= limit:
                        content += f"\n\n[File truncated - {limit} lines shown, more available]"
                    
                    return content if content else "[Empty file]"
                    
            except UnicodeDecodeError:
                return f"Error: '{path}' appears to be a binary file"
                
        except ValueError as e:
            return f"Error: {str(e)}"
        except Exception as e:
            logger.error(f"Read file failed: {str(e)}", exc_info=True)
            return f"Error reading file: {str(e)}"


class WriteFileTool(BaseTool):
    """Tool to write content to a file."""
    
    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="write_file",
            description="Write or overwrite text content to a file. Creates directories if needed. Limited to workspace directory for security.",
            parameters=[
                ToolParameter(
                    name="path",
                    type="string",
                    description="Path to the file (use relative path like 'test.txt' or 'folder/file.txt', NOT absolute paths like '/home/...')",
                    required=True
                ),
                ToolParameter(
                    name="content",
                    type="string",
                    description="Content to write to the file",
                    required=True
                ),
                ToolParameter(
                    name="append",
                    type="boolean",
                    description="If true, append to file instead of overwriting (default: false)",
                    required=False
                )
            ],
            return_type="string"
        )
    
    def execute(self, path: str, content: str, append: bool = False, **kwargs) -> str:
        try:
            file_path = _ensure_safe_path(path)
            
            # Create parent directories
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            mode = 'a' if append else 'w'
            with open(file_path, mode, encoding='utf-8') as f:
                f.write(content)
            
            action = "Appended to" if append else "Wrote"
            size = len(content)
            logger.info(f"{action} file: {file_path} ({size} chars)")
            
            return f"{action} {size} characters to '{path}'"
            
        except ValueError as e:
            return f"Error: {str(e)}"
        except Exception as e:
            logger.error(f"Write file failed: {str(e)}", exc_info=True)
            return f"Error writing file: {str(e)}"


class ListDirectoryTool(BaseTool):
    """Tool to list directory contents."""
    
    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="list_directory",
            description="List files and folders in a directory. Shows file sizes and types. Limited to workspace directory for security.",
            parameters=[
                ToolParameter(
                    name="path",
                    type="string",
                    description="Directory path (use relative path like '.' for root, 'folder/subfolder', NOT absolute paths)",
                    required=False
                ),
                ToolParameter(
                    name="recursive",
                    type="boolean",
                    description="If true, list recursively (default: false)",
                    required=False
                )
            ],
            return_type="string"
        )
    
    def execute(self, path: str = ".", recursive: bool = False, **kwargs) -> str:
        try:
            dir_path = _ensure_safe_path(path)
            
            if not dir_path.exists():
                return f"Error: Directory '{path}' not found"
            
            if not dir_path.is_dir():
                return f"Error: '{path}' is not a directory"
            
            logger.info(f"Listing directory: {dir_path} (recursive={recursive})")
            
            if recursive:
                items = []
                for root, dirs, files in os.walk(dir_path):
                    level = len(Path(root).relative_to(dir_path).parts)
                    indent = "  " * level
                    rel_path = Path(root).relative_to(dir_path) if level > 0 else Path('.')
                    items.append(f"{indent}{rel_path}/")
                    
                    subindent = "  " * (level + 1)
                    for file in files[:50]:  # Limit files per dir
                        file_path = Path(root) / file
                        try:
                            size = file_path.stat().st_size
                            items.append(f"{subindent}{file} ({self._format_size(size)})")
                        except:
                            items.append(f"{subindent}{file}")
                    
                    if len(files) > 50:
                        items.append(f"{subindent}... and {len(files) - 50} more files")
                
                return '\n'.join(items) if items else "[Empty directory]"
            else:
                items = []
                for item in sorted(dir_path.iterdir()):
                    try:
                        if item.is_dir():
                            items.append(f"[DIR]  {item.name}/")
                        else:
                            size = item.stat().st_size
                            items.append(f"[FILE] {item.name} ({self._format_size(size)})")
                    except:
                        items.append(f"      {item.name}")
                
                return '\n'.join(items) if items else "[Empty directory]"
                
        except ValueError as e:
            return f"Error: {str(e)}"
        except Exception as e:
            logger.error(f"List directory failed: {str(e)}", exc_info=True)
            return f"Error listing directory: {str(e)}"
    
    def _format_size(self, size: int) -> str:
        """Format file size human readable."""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"


class SearchFilesTool(BaseTool):
    """Tool to search for files by name pattern."""
    
    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="search_files",
            description="Search for files by name pattern (e.g., '*.py', 'config*'). Limited to workspace directory.",
            parameters=[
                ToolParameter(
                    name="pattern",
                    type="string",
                    description="Search pattern (e.g., '*.txt', '*.py', 'log*')",
                    required=True
                ),
                ToolParameter(
                    name="path",
                    type="string",
                    description="Directory to search in (default: workspace root)",
                    required=False
                )
            ],
            return_type="string"
        )
    
    def execute(self, pattern: str, path: str = ".", **kwargs) -> str:
        try:
            search_path = _ensure_safe_path(path)
            
            if not search_path.exists():
                return f"Error: Directory '{path}' not found"
            
            import fnmatch
            matches = []
            
            for root, dirs, files in os.walk(search_path):
                for filename in fnmatch.filter(files, pattern):
                    full_path = Path(root) / filename
                    rel_path = full_path.relative_to(WORKSPACE_DIR)
                    matches.append(str(rel_path))
                
                # Stop after finding too many
                if len(matches) > 100:
                    matches.append("... (too many results, truncated)")
                    break
            
            if not matches:
                return f"No files matching '{pattern}' found in '{path}'"
            
            logger.info(f"File search: found {len(matches)} matches for '{pattern}' in {search_path}")
            return f"Found {len(matches)} file(s):\n" + '\n'.join(matches)
            
        except ValueError as e:
            return f"Error: {str(e)}"
        except Exception as e:
            logger.error(f"Search files failed: {str(e)}", exc_info=True)
            return f"Error searching files: {str(e)}"


class DeleteFileTool(BaseTool):
    """Tool to delete files (moves to recycle bin)."""
    
    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="delete_file",
            description="Delete a file by moving it to the recycle bin (.recycle folder) with timestamp. Files can be restored from recycle bin. Limited to workspace directory.",
            parameters=[
                ToolParameter(
                    name="path",
                    type="string",
                    description="Path to file to delete (use relative path like 'test.txt' or 'folder/file.txt')",
                    required=True
                )
            ],
            return_type="string"
        )
    
    def execute(self, path: str, **kwargs) -> str:
        try:
            file_path = _ensure_safe_path(path)
            
            if not file_path.exists():
                return f"Error: File '{path}' not found"
            
            if not file_path.is_file():
                return f"Error: '{path}' is not a file (use move/rename for directories)"
            
            # Create timestamped name for recycle bin
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = file_path.name
            recycle_name = f"{timestamp}_{filename}"
            recycle_path = RECYCLE_DIR / recycle_name
            
            # Handle duplicates in recycle bin
            counter = 1
            original_recycle_path = recycle_path
            while recycle_path.exists():
                recycle_path = original_recycle_path.parent / f"{timestamp}_{counter}_{filename}"
                counter += 1
            
            # Move to recycle bin
            import shutil
            shutil.move(str(file_path), str(recycle_path))
            
            logger.info(f"Deleted (recycled) file: {file_path} -> {recycle_path}")
            return f"Deleted '{path}' (moved to .recycle/{recycle_name})"
            
        except ValueError as e:
            return f"Error: {str(e)}"
        except Exception as e:
            logger.error(f"Delete file failed: {str(e)}", exc_info=True)
            return f"Error deleting file: {str(e)}"


class EditFileTool(BaseTool):
    """Surgical find-and-replace edit on an existing file. Token-efficient and safe."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="edit_file",
            description=(
                "Make a precise surgical edit to an existing file by replacing specific text. "
                "PREFER this over write_file when modifying existing files — it only changes what you specify, "
                "preserves the rest, and uses far fewer tokens. "
                "old_string must match exactly (including indentation and whitespace)."
            ),
            parameters=[
                ToolParameter(
                    name="path",
                    type="string",
                    description="Relative path to the file (e.g. 'app/main.py')",
                    required=True,
                ),
                ToolParameter(
                    name="old_string",
                    type="string",
                    description="The exact text to find and replace. Must be unique in the file — add extra surrounding lines if needed to make it unique.",
                    required=True,
                ),
                ToolParameter(
                    name="new_string",
                    type="string",
                    description="The replacement text. Use empty string to delete old_string.",
                    required=True,
                ),
                ToolParameter(
                    name="replace_all",
                    type="boolean",
                    description="If true, replace every occurrence. Default false (replace first only).",
                    required=False,
                ),
            ],
            return_type="string",
        )

    def execute(self, path: str, old_string: str, new_string: str, replace_all: bool = False, **kwargs) -> str:
        try:
            file_path = _ensure_safe_path(path)

            if not file_path.exists():
                return f"Error: File '{path}' not found. Use write_file to create it first."

            content = file_path.read_text(encoding="utf-8", errors="ignore")

            if old_string not in content:
                return (
                    f"Error: Could not find the specified text in '{path}'. "
                    "Make sure old_string matches exactly — check indentation, spaces, and line endings."
                )

            count = content.count(old_string)
            if count > 1 and not replace_all:
                return (
                    f"Error: Found {count} occurrences of that text in '{path}'. "
                    "Add more surrounding lines to old_string to make it unique, or set replace_all=true."
                )

            new_content = content.replace(old_string, new_string) if replace_all else content.replace(old_string, new_string, 1)
            file_path.write_text(new_content, encoding="utf-8")

            replaced = count if replace_all else 1
            logger.info(f"edit_file: replaced {replaced} occurrence(s) in {file_path}")
            return f"Successfully edited '{path}' ({replaced} replacement(s))."

        except ValueError as e:
            return f"Error: {e}"
        except Exception as e:
            logger.error(f"edit_file failed: {e}", exc_info=True)
            return f"Error editing file: {e}"


class MoveRenameTool(BaseTool):
    """Tool to move or rename files and directories."""
    
    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="move_rename",
            description="Move or rename a file or directory. Can move between folders or rename in place. Limited to workspace directory.",
            parameters=[
                ToolParameter(
                    name="source",
                    type="string",
                    description="Source path (use relative path like 'oldname.txt' or 'folder/file')",
                    required=True
                ),
                ToolParameter(
                    name="destination",
                    type="string",
                    description="Destination path (use relative path like 'newname.txt' or 'newfolder/file')",
                    required=True
                )
            ],
            return_type="string"
        )
    
    def execute(self, source: str, destination: str, **kwargs) -> str:
        try:
            source_path = _ensure_safe_path(source)
            dest_path = _ensure_safe_path(destination)
            
            if not source_path.exists():
                return f"Error: Source '{source}' not found"
            
            # Create parent directories if needed
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Check if destination already exists
            if dest_path.exists():
                return f"Error: Destination '{destination}' already exists"
            
            import shutil
            
            if source_path.is_file():
                shutil.move(str(source_path), str(dest_path))
                action = "Moved/renamed"
            else:
                shutil.move(str(source_path), str(dest_path))
                action = "Moved/renamed directory"
            
            logger.info(f"{action}: {source_path} -> {dest_path}")
            return f"{action} '{source}' to '{destination}'"
            
        except ValueError as e:
            return f"Error: {str(e)}"
        except Exception as e:
            logger.error(f"Move/rename failed: {str(e)}", exc_info=True)
            return f"Error moving/renaming: {str(e)}"
