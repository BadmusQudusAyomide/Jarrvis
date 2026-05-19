"""Test code execution through Agent."""
import sys
sys.path.insert(0, 'app')

from app.agents.core_agent import Agent

def test_agent_code():
    print("Testing code execution through Agent...")
    
    agent = Agent()
    
    # Test 1: Simple calculation request
    print("\n=== Test 1: Run this code: print('Hello') ===")
    result1 = agent.run("Run this code: print('Hello from Jarvis!')", [], "You are Jarvis")
    print(result1)
    
    # Test 2: Math calculation
    print("\n=== Test 2: Calculate 15 * 23 ===")
    result2 = agent.run("Calculate 15 * 23", [], "You are Jarvis")
    print(result2)
    
    # Test 3: Blocked import (should be rejected)
    print("\n=== Test 3: Security test - should block os import ===")
    result3 = agent.run("Run this code: import os; print(os.getcwd())", [], "You are Jarvis")
    print(result3)
    
    print("\n=== All agent tests completed! ===")

if __name__ == "__main__":
    test_agent_code()
