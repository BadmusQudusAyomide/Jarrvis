"""Test browser tool calling through the chat endpoint."""
import requests
import json

def test_browser_tool_call():
    print("Testing browser tool calling via chat endpoint...")
    
    url = "http://127.0.0.1:8000/chat"
    payload = {
        "message": "Open browser to https://google.com",
        "session_id": "test"
    }
    
    try:
        response = requests.post(url, json=payload)
        result = response.json()
        print(f"Status: {response.status_code}")
        print(f"Response: {result}")
        
        if response.status_code == 200:
            print("✅ Chat endpoint responded!")
            
            # Check if browser tool was called
            if "browser_open" in str(result) or "Chrome" in str(result):
                print("✅ Browser tool appears to have been called!")
            else:
                print("❌ Browser tool was not called")
        else:
            print(f"❌ Error: {response.status_code}")
            
    except Exception as e:
        print(f"❌ Test failed: {e}")

if __name__ == "__main__":
    test_browser_tool_call()
