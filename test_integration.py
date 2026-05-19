"""Test execute_code integration."""
import sys
sys.path.insert(0, 'app')

from app.tools.system_tools import execute_tool

# Test through system integration
print("Testing execute_code through system integration...")

result = execute_tool('execute_code', {
    'code': 'print("Integration test successful!")\nx = 5\nprint(f"5 squared is {x**2}")'
})

print("\n=== Result ===")
print(result)
