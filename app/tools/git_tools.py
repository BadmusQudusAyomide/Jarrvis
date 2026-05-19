"""Git tools for repository management using GitPython."""
import logging
import os
from pathlib import Path
from typing import Optional, List
import git
from git import Repo, InvalidGitRepositoryError
from app.tools.base import BaseTool, ToolSchema, ToolParameter

logger = logging.getLogger(__name__)

# Allowed directories for safety checks
ALLOWED_DIRS = [
    Path(r'C:\Users\HP\Documents\Jarvis'),  # Jarvis project itself
    Path(r'C:\Users\HP\Documents\Jarvis\workspace'),  # Workspace subfolder
    Path(r'C:\Users\HP\Documents'),  # Parent directory for other projects
]


def _ensure_safe_path(repo_path: str) -> Path:
    """Ensure the repository path is within allowed directories.
    
    Args:
        repo_path: Path to the repository
        
    Returns:
        Resolved Path object
        
    Raises:
        ValueError: If path is outside allowed directories
    """
    path = Path(repo_path).resolve()
    
    # Check if path is within any allowed directory
    for allowed_dir in ALLOWED_DIRS:
        try:
            path.relative_to(allowed_dir)
            return path  # Path is safe
        except ValueError:
            continue  # Try next allowed directory
    
    # Path is not in any allowed directory
    raise ValueError(f"Repository path must be within: {', '.join(str(d) for d in ALLOWED_DIRS)}")


def _get_repo(repo_path: str) -> Repo:
    """Get a Git repository object with safety checks.
    
    Args:
        repo_path: Path to the repository
        
    Returns:
        GitPython Repo object
        
    Raises:
        ValueError: If path is outside workspace or not a git repo
    """
    safe_path = _ensure_safe_path(repo_path)
    
    if not safe_path.exists():
        raise ValueError(f"Repository path does not exist: {safe_path}")
    
    try:
        return Repo(safe_path)
    except InvalidGitRepositoryError:
        raise ValueError(f"Not a git repository: {safe_path}")


class GitStatusTool(BaseTool):
    """Show git working tree status."""
    
    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="git_status",
            description="Show git working tree status - modified, staged, and untracked files.",
            parameters=[
                ToolParameter(
                    name="repo_path",
                    type="string",
                    description="Path to the git repository",
                    required=True
                )
            ],
            return_type="string"
        )
    
    def execute(self, repo_path: str, **kwargs) -> str:
        try:
            repo = _get_repo(repo_path)
            
            # Get status
            result = []
            result.append(f"📁 Repository: {repo.working_dir}")
            result.append(f"🔀 Branch: {repo.active_branch.name}")
            result.append("")
            
            # Check for untracked files
            untracked = repo.untracked_files
            if untracked:
                result.append(f"📄 Untracked files ({len(untracked)}):")
                for f in untracked[:10]:  # Show first 10
                    result.append(f"   {f}")
                if len(untracked) > 10:
                    result.append(f"   ... and {len(untracked) - 10} more")
                result.append("")
            
            # Check for modified files
            modified = [item.a_path for item in repo.index.diff(None)]
            if modified:
                result.append(f"✏️  Modified but not staged ({len(modified)}):")
                for f in modified[:10]:
                    result.append(f"   {f}")
                if len(modified) > 10:
                    result.append(f"   ... and {len(modified) - 10} more")
                result.append("")
            
            # Check for staged files
            staged = [item.a_path for item in repo.index.diff('HEAD')]
            if staged:
                result.append(f"🟢 Staged for commit ({len(staged)}):")
                for f in staged[:10]:
                    result.append(f"   {f}")
                if len(staged) > 10:
                    result.append(f"   ... and {len(staged) - 10} more")
                result.append("")
            
            if not any([untracked, modified, staged]):
                result.append("✅ Working tree clean - nothing to commit")
            
            logger.info(f"Git status checked for {repo.working_dir}")
            return "\n".join(result)
            
        except Exception as e:
            logger.error(f"Git status failed: {str(e)}", exc_info=True)
            return f"Error: {str(e)}"


class GitLogTool(BaseTool):
    """Show commit history."""
    
    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="git_log",
            description="Show git commit history (last N commits).",
            parameters=[
                ToolParameter(
                    name="repo_path",
                    type="string",
                    description="Path to the git repository",
                    required=True
                ),
                ToolParameter(
                    name="n",
                    type="integer",
                    description="Number of commits to show (default: 10)",
                    required=False
                )
            ],
            return_type="string"
        )
    
    def execute(self, repo_path: str, n: int = 10, **kwargs) -> str:
        try:
            repo = _get_repo(repo_path)
            
            # Get commits
            commits = list(repo.iter_commits('HEAD', max_count=n))
            
            if not commits:
                return "No commits found."
            
            result = []
            result.append(f"📜 Commit History (last {len(commits)} commits):")
            result.append(f"📁 Repository: {repo.working_dir}")
            result.append("")
            result.append("-" * 60)
            
            for i, commit in enumerate(commits, 1):
                result.append(f"\n🔹 Commit {i}")
                result.append(f"   Hash: {commit.hexsha[:7]}")
                result.append(f"   Author: {commit.author}")
                result.append(f"   Date: {commit.committed_datetime.strftime('%Y-%m-%d %H:%M')}")
                result.append(f"   Message: {commit.message.strip()}")
            
            logger.info(f"Git log showed {len(commits)} commits for {repo.working_dir}")
            return "\n".join(result)
            
        except Exception as e:
            logger.error(f"Git log failed: {str(e)}", exc_info=True)
            return f"Error: {str(e)}"


class GitDiffTool(BaseTool):
    """Show git diff (unstaged or staged changes)."""
    
    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="git_diff",
            description="Show git diff - unstaged changes by default, or staged changes if specified.",
            parameters=[
                ToolParameter(
                    name="repo_path",
                    type="string",
                    description="Path to the git repository",
                    required=True
                ),
                ToolParameter(
                    name="staged",
                    type="boolean",
                    description="Show staged changes instead of unstaged (default: False)",
                    required=False
                ),
                ToolParameter(
                    name="file",
                    type="string",
                    description="Show diff for specific file only",
                    required=False
                )
            ],
            return_type="string"
        )
    
    def execute(self, repo_path: str, staged: bool = False, file: str = None, **kwargs) -> str:
        try:
            repo = _get_repo(repo_path)
            
            # Get diff
            if staged:
                diff = repo.index.diff('HEAD')
                header = "🟢 Staged changes (ready to commit):"
            else:
                diff = repo.index.diff(None)
                header = "✏️  Unstaged changes:"
            
            if file:
                # Filter to specific file
                diff = [d for d in diff if d.a_path == file or d.b_path == file]
                header += f"\n   File: {file}"
            
            if not diff:
                return f"No {'staged' if staged else 'unstaged'} changes to show."
            
            result = []
            result.append(header)
            result.append("")
            result.append("-" * 60)
            
            for item in diff:
                result.append(f"\n📄 File: {item.a_path}")
                if item.change_type:
                    result.append(f"   Change type: {item.change_type}")
                
                # Try to get actual diff content
                try:
                    if staged:
                        diff_text = repo.git.diff('--cached', item.a_path)
                    else:
                        diff_text = repo.git.diff(item.a_path)
                    
                    if diff_text:
                        # Truncate if too long
                        lines = diff_text.split('\n')
                        if len(lines) > 50:
                            result.append(f"   Diff ({len(lines)} lines, showing first 50):")
                            result.append('\n'.join(lines[:50]))
                            result.append("   ... (truncated)")
                        else:
                            result.append(f"   Diff:")
                            result.append(diff_text)
                except Exception as e:
                    result.append(f"   (Could not get diff: {e})")
                
                result.append("")
            
            logger.info(f"Git diff showed {len(diff)} files for {repo.working_dir}")
            return "\n".join(result)
            
        except Exception as e:
            logger.error(f"Git diff failed: {str(e)}", exc_info=True)
            return f"Error: {str(e)}"


class GitAddTool(BaseTool):
    """Stage files for commit."""
    
    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="git_add",
            description="Stage files for commit (git add).",
            parameters=[
                ToolParameter(
                    name="repo_path",
                    type="string",
                    description="Path to the git repository",
                    required=True
                ),
                ToolParameter(
                    name="files",
                    type="string",
                    description="Files to stage (comma-separated, or '.' for all)",
                    required=True
                )
            ],
            return_type="string"
        )
    
    def execute(self, repo_path: str, files: str, **kwargs) -> str:
        try:
            repo = _get_repo(repo_path)
            
            # Parse files
            if files.strip() == '.':
                # Stage all
                repo.git.add('.')
                logger.info(f"Staged all files in {repo.working_dir}")
                return "✅ Staged all changes (git add .)"
            else:
                file_list = [f.strip() for f in files.split(',')]
                for f in file_list:
                    repo.git.add(f)
                logger.info(f"Staged {len(file_list)} files in {repo.working_dir}")
                return f"✅ Staged {len(file_list)} file(s): {', '.join(file_list)}"
            
        except Exception as e:
            logger.error(f"Git add failed: {str(e)}", exc_info=True)
            return f"Error: {str(e)}"


class GitCommitTool(BaseTool):
    """Commit staged changes."""
    
    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="git_commit",
            description="Commit staged changes with a message.",
            parameters=[
                ToolParameter(
                    name="repo_path",
                    type="string",
                    description="Path to the git repository",
                    required=True
                ),
                ToolParameter(
                    name="message",
                    type="string",
                    description="Commit message",
                    required=True
                )
            ],
            return_type="string"
        )
    
    def execute(self, repo_path: str, message: str, **kwargs) -> str:
        try:
            repo = _get_repo(repo_path)
            
            # Check if there are staged changes
            staged = list(repo.index.diff('HEAD'))
            if not staged and not repo.untracked_files:
                return "❌ No changes to commit. Stage files first with git_add."
            
            # Commit
            new_commit = repo.index.commit(message)
            
            logger.info(f"Committed to {repo.working_dir}: {message}")
            return f"✅ Committed: {message}\n   Hash: {new_commit.hexsha[:7]}"
            
        except Exception as e:
            logger.error(f"Git commit failed: {str(e)}", exc_info=True)
            return f"Error: {str(e)}"


class GitPushTool(BaseTool):
    """Push commits to remote."""
    
    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="git_push",
            description="Push commits to remote repository.",
            parameters=[
                ToolParameter(
                    name="repo_path",
                    type="string",
                    description="Path to the git repository",
                    required=True
                ),
                ToolParameter(
                    name="remote",
                    type="string",
                    description="Remote name (default: origin)",
                    required=False
                ),
                ToolParameter(
                    name="branch",
                    type="string",
                    description="Branch to push (default: current branch)",
                    required=False
                )
            ],
            return_type="string"
        )
    
    def execute(self, repo_path: str, remote: str = 'origin', branch: str = None, **kwargs) -> str:
        try:
            repo = _get_repo(repo_path)
            
            if not branch:
                branch = repo.active_branch.name
            
            # Push
            remote_obj = repo.remote(remote)
            push_info = remote_obj.push(branch)
            
            # Check result
            for info in push_info:
                if info.flags & info.ERROR:
                    return f"❌ Push failed: {info.summary}"
            
            logger.info(f"Pushed {branch} to {remote} for {repo.working_dir}")
            return f"✅ Pushed {branch} to {remote}"
            
        except Exception as e:
            logger.error(f"Git push failed: {str(e)}", exc_info=True)
            return f"Error: {str(e)}"


class GitPullTool(BaseTool):
    """Pull changes from remote."""
    
    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="git_pull",
            description="Pull changes from remote repository.",
            parameters=[
                ToolParameter(
                    name="repo_path",
                    type="string",
                    description="Path to the git repository",
                    required=True
                ),
                ToolParameter(
                    name="remote",
                    type="string",
                    description="Remote name (default: origin)",
                    required=False
                ),
                ToolParameter(
                    name="branch",
                    type="string",
                    description="Branch to pull (default: current branch)",
                    required=False
                )
            ],
            return_type="string"
        )
    
    def execute(self, repo_path: str, remote: str = 'origin', branch: str = None, **kwargs) -> str:
        try:
            repo = _get_repo(repo_path)
            
            if not branch:
                branch = repo.active_branch.name
            
            # Pull
            remote_obj = repo.remote(remote)
            fetch_info = remote_obj.pull(branch)
            
            result = [f"✅ Pulled from {remote}/{branch}"]
            
            for info in fetch_info:
                if info.flags & info.ERROR:
                    return f"❌ Pull failed: {info.note}"
                if info.commit:
                    result.append(f"   {info.commit.hexsha[:7]}: {info.commit.message.strip()}")
            
            logger.info(f"Pulled from {remote}/{branch} for {repo.working_dir}")
            return "\n".join(result)
            
        except Exception as e:
            logger.error(f"Git pull failed: {str(e)}", exc_info=True)
            return f"Error: {str(e)}"


class GitCheckoutTool(BaseTool):
    """Switch to or create a branch."""
    
    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="git_checkout",
            description="Switch to an existing branch or create a new one.",
            parameters=[
                ToolParameter(
                    name="repo_path",
                    type="string",
                    description="Path to the git repository",
                    required=True
                ),
                ToolParameter(
                    name="branch",
                    type="string",
                    description="Branch name to switch to or create",
                    required=True
                ),
                ToolParameter(
                    name="create",
                    type="boolean",
                    description="Create the branch if it doesn't exist (default: False)",
                    required=False
                )
            ],
            return_type="string"
        )
    
    def execute(self, repo_path: str, branch: str, create: bool = False, **kwargs) -> str:
        try:
            repo = _get_repo(repo_path)
            
            if create:
                # Create and checkout new branch
                new_branch = repo.create_head(branch)
                new_branch.checkout()
                logger.info(f"Created and switched to branch {branch} in {repo.working_dir}")
                return f"✅ Created and switched to branch: {branch}"
            else:
                # Checkout existing branch
                repo.git.checkout(branch)
                logger.info(f"Switched to branch {branch} in {repo.working_dir}")
                return f"✅ Switched to branch: {branch}"
            
        except Exception as e:
            logger.error(f"Git checkout failed: {str(e)}", exc_info=True)
            return f"Error: {str(e)}"


class GitCreateBranchTool(BaseTool):
    """Create a new branch (without switching to it)."""
    
    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="git_create_branch",
            description="Create a new branch without switching to it.",
            parameters=[
                ToolParameter(
                    name="repo_path",
                    type="string",
                    description="Path to the git repository",
                    required=True
                ),
                ToolParameter(
                    name="branch",
                    type="string",
                    description="New branch name",
                    required=True
                ),
                ToolParameter(
                    name="from_branch",
                    type="string",
                    description="Base branch to create from (default: current branch)",
                    required=False
                )
            ],
            return_type="string"
        )
    
    def execute(self, repo_path: str, branch: str, from_branch: str = None, **kwargs) -> str:
        try:
            repo = _get_repo(repo_path)
            
            if from_branch:
                # Create from specific branch
                base = repo.heads[from_branch]
                new_branch = repo.create_head(branch, base)
            else:
                # Create from current HEAD
                new_branch = repo.create_head(branch)
            
            logger.info(f"Created branch {branch} in {repo.working_dir}")
            return f"✅ Created branch: {branch}"
            
        except Exception as e:
            logger.error(f"Git create branch failed: {str(e)}", exc_info=True)
            return f"Error: {str(e)}"
