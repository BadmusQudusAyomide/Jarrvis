"""Test codebase indexing and search."""
import sys
sys.path.insert(0, 'app')

from app.tools.codebase_tools import IndexCodebaseTool, SearchCodebaseTool, GetFileSummaryTool

print("=" * 70)
print("CODEBASE INDEXING & SEARCH TEST")
print("=" * 70)

# Test 1: Index the Jarvis codebase
print("\n[Test 1] Indexing Jarvis codebase...")
print("-" * 70)

index_tool = IndexCodebaseTool()
result1 = index_tool.execute(
    directory='c:\\Users\\HP\\Documents\\Jarvis\\app',
    extensions='.py',
    chunk_size=50
)
print(result1)

# Test 2: Search for auth logic
print("\n[Test 2] Searching for 'authentication logic'...")
print("-" * 70)

search_tool = SearchCodebaseTool()
result2 = search_tool.execute(
    query='authentication google oauth',
    n_results=3
)
print(result2)

# Test 3: Search for email tools
print("\n[Test 3] Searching for 'email send'...")
print("-" * 70)

result3 = search_tool.execute(
    query='send email gmail',
    n_results=3
)
print(result3)

# Test 4: Get file summary
print("\n[Test 4] Get summary of gmail_tools.py...")
print("-" * 70)

summary_tool = GetFileSummaryTool()
result4 = summary_tool.execute(
    filepath='c:\\Users\\HP\\Documents\\Jarvis\\app\\tools\\gmail_tools.py'
)
print(result4)

print("\n" + "=" * 70)
print("ALL TESTS COMPLETED!")
print("=" * 70)
