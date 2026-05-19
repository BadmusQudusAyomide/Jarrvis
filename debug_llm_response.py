"""Debug what the LLM is actually returning for browser requests."""
import requests
import json

def debug_llm_response():
    print("Debugging LLM response for browser request...")
    
    url = "http://127.0.0.1:8000/chat"
    payload = {
        "message": "Open browser to https://google.com",
        "session_id": "debug"
    }
    
    try:
        response = requests.post(url, json=payload)
        result = response.json()
        print(f"Raw response: {result}")
        print(f"Response type: {type(result)}")
        
        if 'response' in result:
            print(f"LLM returned: {result['response']}")
            
            # Try to parse as JSON to see format
            try:
                parsed = json.loads(result['response'])
                print(f"Parsed JSON: {parsed}")
                print(f"Type field: {parsed.get('type')}")
            except:
                print("Response is not valid JSON")
        
    except Exception as e:
        print(f"Debug failed: {e}")

if __name__ == "__main__":
    debug_llm_response()
