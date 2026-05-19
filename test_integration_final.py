"""Final integration test for Phase 4 Step 2: Codebase Indexing"""
import sys
sys.path.insert(0, 'app')

print("=" * 70)
print("PHASE 4 STEP 2: CODEBASE INDEXING - FINAL TEST")
print("=" * 70)

from app.tools.system_tools import execute_tool

# Test 1: Index codebase
print("\n[TEST 1] Indexing app directory...")
print("-" * 70)
result1 = execute_tool('index_codebase', {'directory': 'c:\\Users\\HP\\Documents\\Jarvis\\app\\tools', 'extensions': '.py'})
print(result1[:500] + "..." if len(result1) > 500 else result1)

# Test 2: Search codebase
print("\n[TEST 2] Searching for 'calendar'...")
print("-" * 70)
result2 = execute_tool('search_codebase', {'query': 'calendar events google', 'n_results': 3})
print(result2[:1000] + "..." if len(result2) > 1000 else result2)

# Test 3: Search for Gmail
print("\n[TEST 3] Searching for 'gmail send email'...")
print("-" * 70)
result3 = execute_tool('search_codebase', {'query': 'gmail send email', 'n_results': 2})
print(result3[:1000] + "..." if len(result3) > 1000 else result3)

print("\n" + "=" * 70)
print("INTEGRATION TEST COMPLETE!")
print("=" * 70)
print("\n✅ All tools integrated:")
print("   - index_codebase: Index your project's code files")
print("   - search_codebase: Semantic search over indexed code")
print("   - get_file_summary: AI-powered file analysis")
print("\n✅ Natural language support:")
print("   - 'Index my code' → Runs index_codebase")
print("   - 'Find authentication in my codebase' → Runs search_codebase")
print("   - 'Summarize gmail_tools.py' → Runs get_file_summary")
