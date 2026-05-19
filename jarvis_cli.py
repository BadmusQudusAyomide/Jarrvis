import argparse
import requests
import sys
import os

API_URL = "http://127.0.0.1:8080/chat"

def ask_jarvis(message: str, session_id: str = "cli"):
    try:
        response = requests.post(API_URL, json={
            "message": message,
            "session_id": session_id
        })
        return response.json().get("response", "No response")
    except requests.ConnectionError:
        return "Error: Jarvis backend is not running. Start it with: uvicorn app.main:app"

def main():
    parser = argparse.ArgumentParser(prog="jarvis")
    parser.add_argument("message", nargs="+", help="Message to send to Jarvis")
    parser.add_argument("--session", default="cli", help="Session ID")
    args = parser.parse_args()
    
    message = " ".join(args.message)
    
    # Replace '.' with current directory path
    cwd = os.getcwd()
    message = message.replace(" . ", f" {cwd} ").replace("index .", f"index {cwd}")
    
    print(ask_jarvis(message, args.session))

if __name__ == "__main__":
    main()
