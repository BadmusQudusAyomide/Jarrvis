"""Test code execution tool."""
import sys
import os

# Add the app directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

from app.tools.code_tools import ExecuteCodeTool

def test_code_tool():
    print("Testing code execution tool...")
    
    tool = ExecuteCodeTool()
    
    # Test 1: Simple print
    print("\n=== Test 1: Simple print ===")
    code1 = 'print("Hello from sandbox!")\nfor i in range(3):\n    print(f"Number: {i}")'
    result1 = tool.execute(code=code1)
    print(result1)
    
    # Test 2: Math calculation
    print("\n=== Test 2: Math calculation ===")
    code2 = '''
x = 10
y = 20
result = x + y
print(f"{x} + {y} = {result}")
'''
    result2 = tool.execute(code=code2)
    print(result2)
    
    # Test 3: Blocked import (should fail)
    print("\n=== Test 3: Blocked import (should be blocked) ===")
    code3 = 'import os\nprint(os.getcwd())'
    result3 = tool.execute(code=code3)
    print(result3)
    
    # Test 4: Blocked subprocess (should fail)
    print("\n=== Test 4: Blocked subprocess (should be blocked) ===")
    code4 = 'import subprocess\nsubprocess.run(["dir"])'
    result4 = tool.execute(code=code4)
    print(result4)
    
    print("\n=== All tests completed! ===")

if __name__ == "__main__":
    test_code_tool()
