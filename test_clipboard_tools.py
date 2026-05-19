"""Test clipboard tools functionality."""
import sys
import os

# Add the app directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

from app.tools.clipboard_tools import ReadClipboardTool, WriteClipboardTool

def test_clipboard_tools():
    print("Testing clipboard tools...")
    
    # Test write tool
    write_tool = WriteClipboardTool()
    test_text = "Hello from Jarvis clipboard test!"
    result = write_tool.execute(text=test_text)
    print(f"Write result: {result}")
    
    # Test read tool
    read_tool = ReadClipboardTool()
    result = read_tool.execute()
    print(f"Read result: {result}")
    
    print("Clipboard tools test completed!")

if __name__ == "__main__":
    test_clipboard_tools()
