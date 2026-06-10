import httpx
from typing import List, Dict, Any
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS
from jarvis.registry import registry
from jarvis.utils.logging import logger

@registry.register(name="web_search")
def web_search(query: str) -> List[Dict[str, str]]:
    """
    Search the web using DuckDuckGo and return top matching page links and snippets.

    Args:
        query: The search engine query string.
    """
    logger.info(f"Tool call: web_search(query='{query}')")
    try:
        results = []
        with DDGS() as ddgs:
            # Get up to 5 text results
            ddg_generator = ddgs.text(query, max_results=5)
            for r in ddg_generator:
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "snippet": r.get("body", "")
                })
        return results
    except Exception as e:
        logger.error(f"DuckDuckGo search failed: {e}")
        # Return fallback error description inside list
        return [{"error": f"Failed to perform search: {str(e)}"}]

@registry.register(name="open_url")
def open_url(url: str) -> str:
    """
    Fetch the content of a web page and return it as readable plain text.

    Args:
        url: The web URL to fetch.
    """
    logger.info(f"Tool call: open_url(url='{url}')")
    
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5"
    }

    try:
        # Use httpx with follow redirects and a 15-second timeout
        with httpx.Client(follow_redirects=True, headers=headers, timeout=15.0) as client:
            response = client.get(url)
            response.raise_for_status()
            
        # Parse HTML using BeautifulSoup
        soup = BeautifulSoup(response.text, "html.parser")
        
        # Remove script and style elements
        for element in soup(["script", "style", "nav", "footer", "header", "aside"]):
            element.decompose()
            
        # Extract text
        text = soup.get_text(separator="\n")
        
        # Clean up whitespace
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        cleaned_text = "\n".join(lines)
        
        # Limit response length to prevent overwhelming context window (e.g. max ~10k chars)
        max_chars = 12000
        if len(cleaned_text) > max_chars:
            return cleaned_text[:max_chars] + f"\n\n... [TRUNCATED - Content too long, parsed {len(cleaned_text)} characters] ..."
            
        return cleaned_text if cleaned_text else "Page resolved, but no readable text content was found."
        
    except httpx.HTTPStatusError as e:
        return f"HTTP error occurred while fetching url: {e.response.status_code} {e.response.reason_phrase}"
    except httpx.RequestError as e:
        return f"Connection/Network error occurred while fetching url: {str(e)}"
    except Exception as e:
        return f"An unexpected error occurred while parsing url: {str(e)}"
