"""Test calling browser tool directly via the system."""
from app.tools.system_tools import execute_tool

def test_direct_tool_call():
    print("Testing direct browser tool call...")
    
    try:
        result = execute_tool("browser_open", {"url": "https://google.com"})
        print(f"Direct tool call result: {result}")
        
        if "Opened" in result and "Google" in result:
            print("✅ Direct browser tool call works!")
        else:
            print("❌ Direct browser tool call failed")
            
    except Exception as e:
        print(f"❌ Direct tool call error: {e}")

if __name__ == "__main__":
    test_direct_tool_call()
