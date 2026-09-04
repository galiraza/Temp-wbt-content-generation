"""Resolves a Fathom meeting URL into its transcript via the shared n8n
webhook — used to pull meeting context into logo generation before the
images are generated. No authentication on the webhook.
"""

from typing import Optional

import requests

from app.config import FATHOM_TRANSCRIPT_WEBHOOK_URL

_TIMEOUT = 90  # transcript generation can take a while for longer meetings


def fetch_transcript(meeting_url: str) -> Optional[str]:
    """Returns the meeting transcript, or None if the lookup fails for any
    reason (bad URL, webhook error, timeout) — logo generation proceeds
    without meeting context rather than blocking the whole request on this
    being unavailable.
    """
    try:
        response = requests.post(
            FATHOM_TRANSCRIPT_WEBHOOK_URL,
            json={"meeting-url": meeting_url},
            timeout=_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError):
        return None

    if not isinstance(data, list) or not data:
        return None

    result = data[0]
    if result.get("error"):
        return None

    transcript = result.get("meeting-transcript")
    return transcript or None
