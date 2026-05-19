"""Test browser tools through the API directly."""
import requests
import json

def test_browser_api():
    print("Testing browser tools via API...")
    
    # Test browser_open tool directly
    url = "http://127.0.0.1:8000/tools/execute"
    payload = {
        "tool": "browser_open",
        "args": {"url": "https://google.com"}
    }
    
    try:
        response = requests.post(url, json=payload)
        result = response.json()
        print(f"API Result: {result}")
        
        if response.status_code == 200:
            print("✅ Browser tool works via API!")
        else:
            print(f"❌ API Error: {response.status_code}")
            
    except Exception as e:
        print(f"❌ API Test Failed: {e}")

if __name__ == "__main__":
    test_browser_api()
