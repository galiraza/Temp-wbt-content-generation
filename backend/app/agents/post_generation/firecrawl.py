"""Scrapes the client's public reviews page via Firecrawl.

Ported from the WF4 "Scraped Reviews" node, including its options: markdown
output, main content only, and a render wait — review widgets are almost always
client-rendered, so without the wait the page comes back as an empty shell.
"""

import logging
from typing import Optional

import requests

from app.config import FIRECRAWL_API_KEY
from app.errors import ServiceNotConfiguredError, UpstreamServiceError

logger = logging.getLogger("app")

_ENDPOINT = "https://api.firecrawl.dev/v1/scrape"
_RENDER_WAIT_MS = 6000  # WF4 used 6s; review widgets need time to hydrate
_TIMEOUT_SECONDS = 120


def scrape_reviews_page(url: str) -> str:
    """Returns the page as markdown.

    Raises rather than returning empty: the review manager treats a failed scrape
    as a recorded failure on reviews_status, because writing eight reviews from
    nothing would mean inventing them, and the prompt forbids that.
    """
    if not FIRECRAWL_API_KEY:
        raise ServiceNotConfiguredError(
            "Review scraping",
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
                "onlyMainContent": True,
                "waitFor": _RENDER_WAIT_MS,
            },
            timeout=_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        raise UpstreamServiceError(
            "Review scraping",
            "Couldn't read the reviews page. Check the URL is public and try again.",
            internal=f"firecrawl {url}: {exc}",
        ) from exc
    except ValueError as exc:
        raise UpstreamServiceError(
            "Review scraping",
            "The reviews page came back unreadable. Please try again.",
            internal=f"firecrawl {url}: bad JSON: {exc}",
        ) from exc

    markdown = ((payload or {}).get("data") or {}).get("markdown") or ""
    if not markdown.strip():
        raise UpstreamServiceError(
            "Review scraping",
            "No review text was found on that page. Check the reviews page URL.",
            internal=f"firecrawl {url}: empty markdown",
        )
    logger.info("firecrawl_ok url=%s chars=%s", url, len(markdown))
    return markdown


def platform_from_url(url: Optional[str]) -> Optional[str]:
    """Best-effort label for where the reviews came from.

    No agent in the workflow produces this, so it is derived from the host rather
    than generated: "Google", "Trustpilot", "Facebook", or the bare domain.
    """
    if not url:
        return None
    host = url.split("//")[-1].split("/")[0].lower().removeprefix("www.")
    known = {
        "google.com": "Google",
        "google.co.uk": "Google",
        "trustpilot.com": "Trustpilot",
        "uk.trustpilot.com": "Trustpilot",
        "facebook.com": "Facebook",
        "checkatrade.com": "Checkatrade",
        "trustatrader.com": "TrustATrader",
        "yell.com": "Yell",
    }
    for domain, label in known.items():
        if host == domain or host.endswith("." + domain):
            return label
    return host or None
