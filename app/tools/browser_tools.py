"""Browser automation tools using Playwright."""
import os
import logging
import asyncio
import threading
from typing import Optional, List
from app.tools.base import BaseTool, ToolSchema, ToolParameter

logger = logging.getLogger(__name__)

_loop_thread = None
_loop = None
_loop_ready = threading.Event()


def _loop_worker():
    """Background thread worker that owns the browser event loop."""
    global _loop
    _loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_loop)
    _loop_ready.set()
    _loop.run_forever()


def _ensure_loop():
    """Ensure the dedicated background event loop is running."""
    global _loop_thread
    if _loop_thread is None or not _loop_thread.is_alive():
        _loop_ready.clear()
        _loop_thread = threading.Thread(target=_loop_worker, daemon=True)
        _loop_thread.start()
        _loop_ready.wait()


def _run_async(coro):
    """Run async coroutine on a single dedicated background event loop."""
    _ensure_loop()
    future = asyncio.run_coroutine_threadsafe(coro, _loop)
    return future.result()

# Global browser instance (persistent session)
_browser = None
_page = None
_playwright = None

async def get_browser():
    """Get or create persistent browser instance."""
    global _browser, _page, _playwright

    # Recreate browser/page if missing or disconnected.
    needs_create = (
        _browser is None
        or not _browser.is_connected()
        or _page is None
        or _page.is_closed()
    )

    if needs_create:
        try:
            # Clean stale references first.
            _browser = None
            _page = None
            from playwright.async_api import async_playwright
            if _playwright is None:
                _playwright = await async_playwright().start()
            
            # Headless mode from env
            headless = os.getenv("BROWSER_HEADLESS", "false").lower() == "true"
            
            # Launch browser
            _browser = await _playwright.chromium.launch(
                headless=headless,
                slow_mo=100  # Small delay for visibility
            )
            
            # Create page
            _page = await _browser.new_page()
            
            # Set default viewport
            await _page.set_viewport_size({"width": 1280, "height": 720})
            
            logger.info(f"Browser started (headless={headless})")
            
        except Exception as e:
            logger.error(f"Failed to start browser: {str(e)}", exc_info=True)
            raise
    
    return _browser, _page


class BrowserOpenTool(BaseTool):
    """Open a URL in the browser."""
    
    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="browser_open",
            description="Open a URL in the browser. Creates a new page if needed.",
            parameters=[
                ToolParameter(
                    name="url",
                    type="string",
                    description="URL to open (e.g., 'https://google.com', 'https://github.com')",
                    required=True
                )
            ],
            return_type="string"
        )
    
    def execute(self, url: str, **kwargs) -> str:
        return _run_async(self._execute_async(url, **kwargs))

    async def _execute_async(self, url: str, **kwargs) -> str:
        try:
            browser, page = await get_browser()
            
            # Ensure URL has protocol
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url
            
            await page.goto(url, wait_until="domcontentloaded")
            
            # Get page title
            title = await page.title()
            
            logger.info(f"Opened URL: {url} - Title: {title}")
            return f"Opened {url}\nPage title: {title}"
            
        except Exception as e:
            logger.error(f"Failed to open URL {url}: {str(e)}", exc_info=True)
            return f"Error opening URL: {str(e)}"


class BrowserGetTextTool(BaseTool):
    """Extract visible text from the current page."""
    
    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="browser_get_text",
            description="Extract visible text from the current browser page.",
            parameters=[
                ToolParameter(
                    name="selector",
                    type="string",
                    description="CSS selector to get text from specific element (optional, gets full page text if not provided)",
                    required=False
                )
            ],
            return_type="string"
        )
    
    def execute(self, selector: str = None, **kwargs) -> str:
        return _run_async(self._execute_async(selector, **kwargs))

    async def _execute_async(self, selector: str = None, **kwargs) -> str:
        try:
            browser, page = await get_browser()
            
            if selector:
                # Get text from specific element
                element = await page.wait_for_selector(selector, timeout=5000)
                text = await element.text_content()
                logger.info(f"Got text from selector '{selector}'")
                return f"Text from {selector}:\n{text}"
            else:
                # Get full page text
                text = await page.inner_text('body')
                
                # Limit output
                if len(text) > 2000:
                    text = text[:2000] + "\n... (text truncated)"
                
                logger.info("Got full page text")
                return f"Page text:\n{text}"
                
        except Exception as e:
            logger.error(f"Failed to get text: {str(e)}", exc_info=True)
            return f"Error getting text: {str(e)}"


class BrowserScreenshotTool(BaseTool):
    """Take a screenshot of the current page."""
    
    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="browser_screenshot",
            description="Take a screenshot of the current browser page.",
            parameters=[
                ToolParameter(
                    name="filename",
                    type="string",
                    description="Screenshot filename (e.g., 'screenshot.png'). Defaults to 'screenshot.png'",
                    required=False
                )
            ],
            return_type="string"
        )
    
    def execute(self, filename: str = "screenshot.png", **kwargs) -> str:
        return _run_async(self._execute_async(filename, **kwargs))

    async def _execute_async(self, filename: str, **kwargs) -> str:
        try:
            browser, page = await get_browser()
            
            # Ensure filename ends with .png
            if not filename.lower().endswith('.png'):
                filename += '.png'
            
            # Save to workspace
            workspace_dir = os.getenv("JARVIS_WORKSPACE", r"C:\Users\HP\Documents\Jarvis")
            screenshot_path = os.path.join(workspace_dir, filename)
            
            await page.screenshot(path=screenshot_path, full_page=True)
            
            logger.info(f"Screenshot saved: {screenshot_path}")
            return f"Screenshot saved to {screenshot_path}"
            
        except Exception as e:
            logger.error(f"Failed to take screenshot: {str(e)}", exc_info=True)
            return f"Error taking screenshot: {str(e)}"


class BrowserClickTool(BaseTool):
    """Click an element on the page."""
    
    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="browser_click",
            description="Click an element by CSS selector or text.",
            parameters=[
                ToolParameter(
                    name="selector",
                    type="string",
                    description="CSS selector of element to click (e.g., 'button', '#submit', '.login-btn')",
                    required=True
                )
            ],
            return_type="string"
        )
    
    def execute(self, selector: str, **kwargs) -> str:
        return _run_async(self._execute_async(selector, **kwargs))

    async def _execute_async(self, selector: str, **kwargs) -> str:
        try:
            browser, page = await get_browser()

            selector = (selector or "").strip()
            candidate_selectors = [selector] if selector else []

            # Common search-button fallbacks for Google.
            if selector in {"input[name='btnK']", "button[name='btnK']"}:
                candidate_selectors.extend([
                    "input[name='btnK']",
                    "button[name='btnK']",
                    "input[aria-label='Google Search']",
                    "button:has-text('Google Search')"
                ])

            # Deduplicate selectors
            seen = set()
            ordered = []
            for s in candidate_selectors:
                if s and s not in seen:
                    seen.add(s)
                    ordered.append(s)

            last_error = None
            for candidate in ordered:
                try:
                    locator = page.locator(candidate).first
                    await locator.wait_for(state="attached", timeout=3000)
                    # Try normal click first; fallback to force click for tricky overlays/visibility.
                    try:
                        await locator.click(timeout=3000)
                    except Exception:
                        await locator.click(timeout=3000, force=True)
                    logger.info(f"Clicked element: {candidate}")
                    return f"Clicked element: {candidate}"
                except Exception as e:
                    last_error = e
                    continue

            # Final fallback for search actions: pressing Enter in the search field.
            if selector in {"input[name='btnK']", "button[name='btnK']"}:
                for search_selector in ["textarea[name='q']", "input[name='q']"]:
                    try:
                        search_box = page.locator(search_selector).first
                        await search_box.wait_for(state="visible", timeout=2000)
                        await search_box.press("Enter")
                        logger.info(f"Submitted search with Enter via {search_selector}")
                        return f"Submitted search with Enter via {search_selector}"
                    except Exception:
                        pass

            return f"Error clicking element: {str(last_error)}"
            
        except Exception as e:
            logger.error(f"Failed to click {selector}: {str(e)}", exc_info=True)
            return f"Error clicking element: {str(e)}"


class BrowserFillTool(BaseTool):
    """Fill an input field."""
    
    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="browser_fill",
            description="Fill an input field with text.",
            parameters=[
                ToolParameter(
                    name="selector",
                    type="string",
                    description="CSS selector of input field (e.g., 'input[name=\"username\"]', '#email')",
                    required=True
                ),
                ToolParameter(
                    name="text",
                    type="string",
                    description="Text to fill in the input field",
                    required=True
                )
            ],
            return_type="string"
        )
    
    def execute(self, selector: str, text: str, **kwargs) -> str:
        return _run_async(self._execute_async(selector, text, **kwargs))

    async def _execute_async(self, selector: str, text: str, **kwargs) -> str:
        try:
            browser, page = await get_browser()

            if not text:
                return "Error filling input: text is required"

            selector = (selector or "").strip()
            candidate_selectors = []

            # Normalize weak selectors often emitted by smaller models.
            if selector in {"name", "[name]"}:
                candidate_selectors.extend(["textarea[name='q']", "input[name='q']"])

            if selector:
                candidate_selectors.append(selector)

            # Common search-box fallbacks.
            candidate_selectors.extend([
                "textarea[name='q']",
                "input[name='q']",
                "input[type='search']",
                "textarea[aria-label*='Search']",
                "input[aria-label*='Search']"
            ])

            # De-duplicate while preserving order.
            seen = set()
            ordered_selectors = []
            for s in candidate_selectors:
                if s not in seen:
                    seen.add(s)
                    ordered_selectors.append(s)

            last_error = None
            for candidate in ordered_selectors:
                try:
                    element = await page.wait_for_selector(candidate, timeout=2500)
                    await element.fill(text)
                    logger.info(f"Filled {candidate} with text")
                    return f"Filled {candidate} with text: {text}"
                except Exception as e:
                    last_error = e
                    continue

            return f"Error filling input: {str(last_error)}"
            
        except Exception as e:
            logger.error(f"Failed to fill {selector}: {str(e)}", exc_info=True)
            return f"Error filling input: {str(e)}"


class BrowserCloseTool(BaseTool):
    """Close the browser session."""
    
    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="browser_close",
            description="Close the browser session and clean up resources.",
            parameters=[],
            return_type="string"
        )
    
    def execute(self, **kwargs) -> str:
        return _run_async(self._execute_async(**kwargs))

    async def _execute_async(self, **kwargs) -> str:
        try:
            global _browser, _page, _playwright
            
            if _browser:
                await _browser.close()
                _browser = None
                _page = None
                if _playwright:
                    await _playwright.stop()
                    _playwright = None
                logger.info("Browser closed")
                return "Browser closed successfully"
            else:
                return "Browser is not open"
                
        except Exception as e:
            logger.error(f"Failed to close browser: {str(e)}", exc_info=True)
            return f"Error closing browser: {str(e)}"


class BrowserScrollTool(BaseTool):
    """Scroll the page up or down."""
    
    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="browser_scroll",
            description="Scroll the page up or down.",
            parameters=[
                ToolParameter(
                    name="direction",
                    type="string",
                    description="Scroll direction: 'up', 'down', 'top', or 'bottom'",
                    required=True
                ),
                ToolParameter(
                    name="pixels",
                    type="integer",
                    description="Pixels to scroll (optional, ignored for 'top'/'bottom')",
                    required=False
                )
            ],
            return_type="string"
        )
    
    def execute(self, direction: str, pixels: int = None, **kwargs) -> str:
        return _run_async(self._execute_async(direction, pixels, **kwargs))

    async def _execute_async(self, direction: str, pixels: int, **kwargs) -> str:
        try:
            browser, page = await get_browser()
            
            direction = direction.lower()
            
            if direction == "top":
                await page.evaluate("window.scrollTo(0, 0)")
                return "Scrolled to top of page"
            elif direction == "bottom":
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                return "Scrolled to bottom of page"
            elif direction in ["up", "down"]:
                pixels = pixels or 300
                if direction == "up":
                    pixels = -pixels
                await page.evaluate(f"window.scrollBy(0, {pixels})")
                return f"Scrolled {direction} by {pixels} pixels"
            else:
                return "Invalid direction. Use: up, down, top, or bottom"
                
        except Exception as e:
            logger.error(f"Failed to scroll: {str(e)}", exc_info=True)
            return f"Error scrolling: {str(e)}"


class BrowserExecuteJSTool(BaseTool):
    """Execute JavaScript on the page."""
    
    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="browser_execute_js",
            description="Execute JavaScript code on the current page.",
            parameters=[
                ToolParameter(
                    name="script",
                    type="string",
                    description="JavaScript code to execute (e.g., 'document.title', 'window.location.href')",
                    required=True
                )
            ],
            return_type="string"
        )
    
    def execute(self, script: str, **kwargs) -> str:
        return _run_async(self._execute_async(script, **kwargs))

    async def _execute_async(self, script: str, **kwargs) -> str:
        try:
            browser, page = await get_browser()
            
            # Execute JavaScript
            result = await page.evaluate(script)
            
            logger.info(f"Executed JS: {script}")
            return f"JavaScript result: {result}"
            
        except Exception as e:
            logger.error(f"Failed to execute JS: {str(e)}", exc_info=True)
            return f"Error executing JavaScript: {str(e)}"


class BrowserGetHTMLTool(BaseTool):
    """Get raw HTML of the current page."""
    
    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="browser_get_html",
            description="Get raw HTML of the current page or specific element.",
            parameters=[
                ToolParameter(
                    name="selector",
                    type="string",
                    description="CSS selector to get HTML from specific element (optional, gets full page HTML if not provided)",
                    required=False
                )
            ],
            return_type="string"
        )
    
    def execute(self, selector: str = None, **kwargs) -> str:
        return _run_async(self._execute_async(selector, **kwargs))

    async def _execute_async(self, selector: str, **kwargs) -> str:
        try:
            browser, page = await get_browser()
            
            if selector:
                # Get HTML from specific element
                element = await page.wait_for_selector(selector, timeout=5000)
                html = await element.inner_html()
                logger.info(f"Got HTML from selector '{selector}'")
                return f"HTML from {selector}:\n{html}"
            else:
                # Get full page HTML
                html = await page.content()
                
                # Limit output
                if len(html) > 3000:
                    html = html[:3000] + "\n... (HTML truncated)"
                
                logger.info("Got full page HTML")
                return f"Page HTML:\n{html}"
                
        except Exception as e:
            logger.error(f"Failed to get HTML: {str(e)}", exc_info=True)
            return f"Error getting HTML: {str(e)}"
