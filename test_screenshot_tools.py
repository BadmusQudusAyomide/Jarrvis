"""Test screenshot tools functionality."""
import sys
import os

# Add the app directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

from app.tools.screenshot_tools import ScreenshotTool

def test_screenshot_tool():
    print("Testing screenshot tool...")
    
    # Test screenshot tool
    screenshot_tool = ScreenshotTool()
    result = screenshot_tool.execute(filename="test_screenshot")
    print(f"Screenshot result: {result}")
    
    print("Screenshot tool test completed!")

if __name__ == "__main__":
    test_screenshot_tool()
