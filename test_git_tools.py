"""Test Git tools."""
import sys
sys.path.insert(0, 'app')

from app.tools.git_tools import GitStatusTool, GitLogTool, GitDiffTool
from app.tools.git_tools import GitAddTool, GitCommitTool, GitPushTool, GitPullTool, GitCheckoutTool, GitCreateBranchTool

print("=" * 70)
print("GIT TOOLS TEST")
print("=" * 70)

# Test on Jarvis repo itself (it's a git repo in the parent of workspace)
repo_path = r'C:\Users\HP\Documents\Jarvis'

# Test 1: Git Status
print("\n[TEST 1] Git Status")
print("-" * 70)
try:
    status_tool = GitStatusTool()
    result1 = status_tool.execute(repo_path=repo_path)
    print(result1[:800] + "..." if len(result1) > 800 else result1)
except Exception as e:
    print(f"Error: {e}")

# Test 2: Git Log
print("\n[TEST 2] Git Log (last 5 commits)")
print("-" * 70)
try:
    log_tool = GitLogTool()
    result2 = log_tool.execute(repo_path=repo_path, n=5)
    print(result2[:1000] + "..." if len(result2) > 1000 else result2)
except Exception as e:
    print(f"Error: {e}")

# Test 3: Git Diff (unstaged)
print("\n[TEST 3] Git Diff (unstaged)")
print("-" * 70)
try:
    diff_tool = GitDiffTool()
    result3 = diff_tool.execute(repo_path=repo_path, staged=False)
    print(result3[:1000] + "..." if len(result3) > 1000 else result3)
except Exception as e:
    print(f"Error: {e}")

print("\n" + "=" * 70)
print("WRITE TOOLS - Testing safety checks:")
print("=" * 70)

# Test 4: Safety check - try to access repo outside workspace
print("\n[TEST 4] Safety check - accessing C:\\ (should fail)")
print("-" * 70)
try:
    status_tool = GitStatusTool()
    result4 = status_tool.execute(repo_path=r'C:\\')
    print(result4)
except Exception as e:
    print(f"✅ Correctly blocked: {e}")

print("\n" + "=" * 70)
print("ALL TESTS COMPLETE!")
print("=" * 70)
