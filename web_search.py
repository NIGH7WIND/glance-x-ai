import logging
from tavily import AsyncTavilyClient
import config

logger = logging.getLogger("overlay_assistant.web_search")

async def search(query: str) -> str:
    """
    Executes an async Tavily search for the given query and returns
    a formatted string summary of the top results.
    """
    if not config.TAVILY_API_KEY:
        logger.warning("web_search: TAVILY_API_KEY is not set.")
        return "Error: Tavily API key is missing. Please set the TAVILY_API_KEY environment variable."

    try:
        logger.info(f"web_search: querying Tavily for '{query}'...")
        client = AsyncTavilyClient(api_key=config.TAVILY_API_KEY)
        
        response = await client.search(
            query=query,
            max_results=config.WEB_SEARCH_MAX_RESULTS,
            search_depth="basic",
        )
        
        results = response.get("results", [])
        if not results:
            return "No web search results found for this query."

        formatted_output = []
        for i, res in enumerate(results, 1):
            title = res.get("title", "No Title")
            url = res.get("url", "")
            content = res.get("content", "").strip()
            formatted_output.append(f"{i}. [{title}]({url})\n   {content}")

        return "\n\n".join(formatted_output)

    except Exception as e:
        logger.exception(f"web_search: Error performing search for '{query}': {e}")
        return f"Error executing web search: {str(e)}"