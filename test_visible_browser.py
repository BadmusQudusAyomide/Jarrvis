"""Test visible browser to see if Chrome opens."""
import asyncio
import sys
import os

# Add app to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.tools.browser_tools import BrowserOpenTool

async def test_visible_browser():
    print("Testing visible browser - Chrome should open visibly...")
    
    # Test opening browser
    open_tool = BrowserOpenTool()
    result = await open_tool._execute_async("https://google.com")
    print(f"Result: {result}")
    
    # Keep browser open for 5 seconds so you can see it
    print("Browser will stay open for 5 seconds...")
    await asyncio.sleep(5)
    
    print("Test complete!")

if __name__ == "__main__":
    asyncio.run(test_visible_browser())
