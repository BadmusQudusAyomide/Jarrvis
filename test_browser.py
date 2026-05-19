"""Test browser tools directly."""
import asyncio
import sys
import os

# Add app to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.tools.browser_tools import BrowserOpenTool, BrowserScreenshotTool, BrowserGetTextTool

async def test_browser():
    print("Testing browser tools...")
    
    # Test opening browser
    open_tool = BrowserOpenTool()
    result = await open_tool._execute_async("https://google.com")
    print(f"Open result: {result}")
    
    # Test getting text
    text_tool = BrowserGetTextTool()
    result = await text_tool._execute_async()
    print(f"Text result: {result[:200]}...")
    
    # Test screenshot
    screenshot_tool = BrowserScreenshotTool()
    result = await screenshot_tool._execute_async("test_screenshot.png")
    print(f"Screenshot result: {result}")
    
    print("Browser test complete!")

if __name__ == "__main__":
    asyncio.run(test_browser())
