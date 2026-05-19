"""Web search tools using Tavily API."""
import os
import logging
from tavily import TavilyClient
from app.tools.base import BaseTool, ToolSchema, ToolParameter

logger = logging.getLogger(__name__)


class WebSearchTool(BaseTool):
    """Tool to search the web for current information."""
    
    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="web_search",
            description="Search the internet for current information, news, facts, or up-to-date data. Use when user asks about current events, recent news, or information that may have changed since training.",
            parameters=[
                ToolParameter(
                    name="query",
                    type="string",
                    description="The search query - be specific for better results",
                    required=True
                ),
                ToolParameter(
                    name="max_results",
                    type="integer",
                    description="Number of results to return (1-5, default 3)",
                    required=False
                )
            ],
            return_type="string"
        )
    
    def execute(self, query: str, max_results: int = 3, **kwargs) -> str:
        """Execute web search via Tavily API."""
        try:
            api_key = os.getenv("TAVILY_API_KEY")
            if not api_key:
                logger.error("TAVILY_API_KEY not set")
                return "Error: Web search API key not configured. Set TAVILY_API_KEY in .env file."
            
            client = TavilyClient(api_key=api_key)
            
            # Clamp max_results to reasonable range
            max_results = max(1, min(5, int(max_results)))
            
            logger.info(f"Searching web for: {query} (max_results={max_results})")
            
            response = client.search(
                query=query,
                max_results=max_results,
                search_depth="basic"
            )
            
            results = response.get("results", [])
            if not results:
                return "No results found for this query."
            
            formatted = []
            for i, r in enumerate(results, 1):
                title = r.get('title', 'N/A')
                url = r.get('url', 'N/A')
                content = r.get('content', 'N/A')[:200]  # Limit content length
                
                formatted.append(
                    f"[{i}] {title}\n"
                    f"URL: {url}\n"
                    f"Summary: {content}..."
                )
            
            output = "\n\n".join(formatted)
            logger.info(f"Web search completed, found {len(results)} results")
            return output
            
        except Exception as e:
            logger.error(f"Web search failed: {str(e)}", exc_info=True)
            return f"Error performing web search: {str(e)}"


class WebFetchTool(BaseTool):
    """Tool to fetch and extract content from a specific URL."""
    
    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="web_fetch",
            description="Fetch and extract the main content from a specific URL. Use to read articles, documentation, or web pages when user provides a link or when you need more detail from a search result.",
            parameters=[
                ToolParameter(
                    name="url",
                    type="string",
                    description="The full URL to fetch (must include http:// or https://)",
                    required=True
                )
            ],
            return_type="string"
        )
    
    def execute(self, url: str, **kwargs) -> str:
        """Fetch content from a specific URL using Tavily extract."""
        try:
            api_key = os.getenv("TAVILY_API_KEY")
            if not api_key:
                logger.error("TAVILY_API_KEY not set")
                return "Error: Web fetch API key not configured."
            
            client = TavilyClient(api_key=api_key)
            
            logger.info(f"Fetching URL: {url}")
            
            response = client.extract(
                urls=[url],
                include_images=False
            )
            
            results = response.get("results", [])
            if not results:
                return f"Could not extract content from {url}"
            
            result = results[0]
            content = result.get("raw_content", "")
            
            if not content:
                return f"No content extracted from {url}"
            
            # Limit content length
            if len(content) > 3000:
                content = content[:3000] + "... [truncated]"
            
            logger.info(f"Successfully fetched content from {url}")
            return f"Content from {url}:\n\n{content}"
            
        except Exception as e:
            logger.error(f"Web fetch failed: {str(e)}", exc_info=True)
            return f"Error fetching URL: {str(e)}"
