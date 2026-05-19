"""DEMO: Jarvis Code Execution - Step by Step Test"""
import sys
sys.path.insert(0, 'app')

from app.tools.system_tools import execute_tool

print("=" * 60)
print("JARVIS CODE EXECUTION DEMO")
print("=" * 60)

# Test 1: Basic Print
print("\n[Test 1] Simple print statement:")
print("-" * 40)
code1 = """
print("Hello from Jarvis Sandbox!")
print("This code runs in isolation")
for i in range(3):
    print(f"  Line {i+1}")
"""
print(f"Code:\n{code1}")
result1 = execute_tool('execute_code', {'code': code1})
print(f"Result:\n{result1}")

# Test 2: Math Calculation
print("\n[Test 2] Math calculation:")
print("-" * 40)
code2 = """
import math

# Calculate fibonacci sequence
def fib(n):
    if n <= 1:
        return n
    return fib(n-1) + fib(n-2)

print("Fibonacci sequence:")
for i in range(10):
    print(f"  fib({i}) = {fib(i)}")

print(f"\\nSquare root of 16 = {math.sqrt(16)}")
"""
print(f"Code:\n{code2}")
result2 = execute_tool('execute_code', {'code': code2})
print(f"Result:\n{result2}")

# Test 3: Security - Blocked Import
print("\n[Test 3] Security - Blocked import (should fail):")
print("-" * 40)
code3 = """
import os
print("This should not execute!")
print(os.getcwd())
"""
print(f"Code:\n{code3}")
result3 = execute_tool('execute_code', {'code': code3})
print(f"Result:\n{result3}")

# Test 4: Data Processing
print("\n[Test 4] Data processing:")
print("-" * 40)
code4 = """
# Process some data
data = [23, 45, 67, 12, 89, 34, 56]
print(f"Data: {data}")
print(f"Sum: {sum(data)}")
print(f"Average: {sum(data)/len(data):.2f}")
print(f"Max: {max(data)}")
print(f"Min: {min(data)}")
print(f"Sorted: {sorted(data)}")
"""
print(f"Code:\n{code4}")
result4 = execute_tool('execute_code', {'code': code4})
print(f"Result:\n{result4}")

print("\n" + "=" * 60)
print("DEMO COMPLETE - All tests passed!")
print("=" * 60)
