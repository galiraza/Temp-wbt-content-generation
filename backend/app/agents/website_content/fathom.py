"""Resolving Fathom meeting URLs into summaries and transcripts.

The workflow's intake path, in three n8n nodes:

  "Remove_Url_Parameters"                            url.split("?")[0]
  "Converting_Fathom_Host_and_Url_into_Single_Items" 3 slots -> 3 items
  "Get Summary and Transcript"                       POST the shared n8n webhook

Same webhook app.services.fathom_service already calls for logo generation, but
that helper returns only the transcript and only for one URL. This module keeps
all three slots and both fields, because the analyst prompt reads them as six
separate inputs and treats later meetings as overriding earlier ones.

`Check Error Exist in Items` is reproduced in `collect`: slot 1's errors all
count, while slots 2 and 3 are allowed to say "No meeting URL provided." without
that being an error -- those slots are optional and an empty one is normal. The
difference from n8n is what happens next. There, a real error routed to a Zapier
email and the run stopped. Here the reason is returned alongside whatever was
fetched, and the caller records it as a `note` on the request, matching the
behaviour Command HQ's API documentation already promises callers:

    "This content was generated without a kickoff meeting because: <reason>."
"""

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import List, Optional, Sequence

import requests

from app.config import FATHOM_TRANSCRIPT_WEBHOOK_URL

logger = logging.getLogger("app")

#: Long meetings take a while to come back. The logo path uses 90s for one
#: lookup; three run concurrently here, so each still gets the full budget.
_TIMEOUT = 120

#: The exact string the webhook returns for an empty slot. Matched literally,
#: the same way the n8n Code node did -- any OTHER error on slots 2 and 3 is a
#: real error and is reported.
_NO_URL_ERROR = "No meeting URL provided."

#: The wording Command HQ's callers are already told to expect.
NOTE_TEMPLATE = (
    "This content was generated without a kickoff meeting because: {reason}. "
    "For better, more tailored content, please add a meeting URL or correct the existing one."
)


@dataclass
class Meeting:
    """One slot's result. Both fields are "" when the slot was empty."""

    summary: str = ""
    transcript: str = ""
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return bool(self.summary or self.transcript)


@dataclass
class MeetingSet:
    """All three slots, plus the note to show the user."""

    meetings: List[Meeting] = field(default_factory=list)
    note: Optional[str] = None

    def slot(self, index: int) -> Meeting:
        """1-based, and never raises: an unfilled slot reads as an empty one."""
        if 1 <= index <= len(self.meetings):
            return self.meetings[index - 1]
        return Meeting()

    @property
    def any_fetched(self) -> bool:
        return any(m.ok for m in self.meetings)


def clean_url(url: Optional[str]) -> str:
    """`Remove_Url_Parameters`: everything before the first "?".

    Fathom share links pick up tracking parameters when they are copied out of a
    browser, and the lookup webhook matches on the bare share URL.
    """
    return (url or "").strip().split("?")[0]


def _fetch_one(url: str) -> Meeting:
    """One webhook call. Never raises -- a dead lookup is a note, not a failure."""
    if not url:
        return Meeting(error=_NO_URL_ERROR)

    try:
        response = requests.post(
            FATHOM_TRANSCRIPT_WEBHOOK_URL,
            json={"meeting-url": url},
            timeout=_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        logger.warning("fathom_lookup_failed url=%s error=%s", url, exc)
        return Meeting(error="The meeting lookup service did not respond.")
    except ValueError:
        logger.warning("fathom_lookup_unreadable url=%s", url)
        return Meeting(error="The meeting lookup service returned an unreadable reply.")

    # The webhook answers with a single-element list, the same shape
    # app.services.fathom_service reads.
    result = data[0] if isinstance(data, list) and data else data
    if not isinstance(result, dict):
        return Meeting(error="The meeting lookup service returned an unexpected reply.")

    error = (result.get("error") or "").strip()
    if error:
        return Meeting(error=error)

    return Meeting(
        summary=(result.get("meeting-summary") or "").strip(),
        transcript=(result.get("meeting-transcript") or "").strip(),
    )


def collect(urls: Sequence[Optional[str]]) -> MeetingSet:
    """Fetches up to three meetings at once and builds the user-facing note.

    Concurrent because the three lookups are independent and each can take a
    minute or more. n8n ran them as three items through one HTTP node, which is
    sequential -- three slow meetings cost three timeouts back to back.
    """
    cleaned = [clean_url(url) for url in list(urls)[:3]]
    while len(cleaned) < 3:
        cleaned.append("")

    with ThreadPoolExecutor(max_workers=3) as pool:
        meetings = list(pool.map(_fetch_one, cleaned))

    # `Check Error Exist in Items`, unchanged: slot 1 (index 0) counts every
    # error including the empty-slot one, because a kickoff meeting is what the
    # analyst prompt is built around. Slots 2 and 3 are optional.
    reasons = []
    for index, meeting in enumerate(meetings):
        if not meeting.error:
            continue
        if index > 0 and meeting.error == _NO_URL_ERROR:
            continue
        reasons.append(f"Meeting {index + 1}: {meeting.error}")

    note = NOTE_TEMPLATE.format(reason=" | ".join(reasons)) if reasons else None
    if note:
        logger.info("fathom_note reasons=%s", " | ".join(reasons))
    return MeetingSet(meetings=meetings, note=note)
