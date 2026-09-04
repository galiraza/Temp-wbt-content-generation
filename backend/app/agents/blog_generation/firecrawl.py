"""Scrapes the client's homepage via Firecrawl.

Ported from the n8n node "Scrape a URL and get content as markdown or other
formats", which ran with default options.

Not shared with app.agents.post_generation.firecrawl on purpose: that one passes
`onlyMainContent: True`, which is right for a reviews widget and wrong here. The
website-content prompt explicitly asks for navigation structure, footer content,
contact details and trust badges — all of which "main content only" strips out.
"""

import logging

import requests

from app.config import FIRECRAWL_API_KEY
from app.errors import ServiceNotConfiguredError, UpstreamServiceError

logger = logging.getLogger("app")

_ENDPOINT = "https://api.firecrawl.dev/v1/scrape"
_RENDER_WAIT_MS = 4000
_TIMEOUT_SECONDS = 120


def scrape_homepage(url: str) -> str:
    """Returns the page as markdown.

    Raises rather than returning empty: every blog prompt injects this content as
    the client's context, so writing a cluster from an empty scrape would mean
    inventing the client's services.
    """
    if not FIRECRAWL_API_KEY:
        raise ServiceNotConfiguredError(
            "Website scraping",
            internal="FIRECRAWL_API_KEY is unset",
        )

    try:
        response = requests.post(
            _ENDPOINT,
            headers={
                "Authorization": f"Bearer {FIRECRAWL_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "url": url,
                "formats": ["markdown"],
                # Whole page, not just the article body — see the module docstring.
                "onlyMainContent": False,
                "waitFor": _RENDER_WAIT_MS,
            },
            timeout=_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        raise UpstreamServiceError(
            "Website scraping",
            "Couldn't read that website. Check the URL is public and try again.",
            internal=f"firecrawl {url}: {exc}",
        ) from exc
    except ValueError as exc:
        raise UpstreamServiceError(
            "Website scraping",
            "That website came back unreadable. Please try again.",
            internal=f"firecrawl {url}: bad JSON: {exc}",
        ) from exc

    markdown = ((payload or {}).get("data") or {}).get("markdown") or ""
    if not markdown.strip():
        raise UpstreamServiceError(
            "Website scraping",
            "No content was found on that page. Check the website URL.",
            internal=f"firecrawl {url}: empty markdown",
        )
    logger.info("firecrawl_homepage_ok url=%s chars=%s", url, len(markdown))
    return markdown
