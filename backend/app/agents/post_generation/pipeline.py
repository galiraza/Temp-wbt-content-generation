"""THE PIPELINE - both managers, and how they run.

This is the file to read to understand the whole flow. Everything below is pure:
it takes the request row, calls the two managers, and returns what they produced.
No database writes happen here — app.services.post_generation_service owns those,
which is what lets the two managers run on separate threads without sharing a
SQLAlchemy Session (Sessions are not thread-safe).


    POST /api/post-generation/{id}/generate
                  |
                  v
          run_managers(request)
                  |
        +---------+---------+                    <-- ThreadPoolExecutor(2)
        |                   |                        A and B run TOGETHER
        v                   v
  MANAGER A              MANAGER B
  (8 posts + 4 reels)    (8 reviews)
        |                   |
        |            +------+------+             <-- inner ThreadPoolExecutor(2)
        |            |             |                 scrape and research TOGETHER
        |            v             v
        |      B1 Firecrawl   B2 hashtag chain
        |        scrape       prompt | llm(+search) | text
        |            |             |
        |            +------+------+
        |                   |
        v                   v
  A1 hashtag chain    B3 content chain
  prompt | llm(+search) | text      prompt | llm | ReviewListParser()
        |                   |
        v                   |
  A2 content chain          |
  prompt | llm | text       |
        |                   |
        v                   |
  parsed TWICE              |
  parse_posts -> 8          |
  parse_reels -> 4          |
        |                   |
        v                   v
  fit to slots         renumber 1-8
  1,3,4,6,7,8,10,12    derive platform
  and 2,5,9,11
        |                   |
        +---------+---------+
                  |
                  v
          GenerationOutcome
        (posts, reels, reviews, pools,
         scraped markdown, errors)
                  |
                  v
      the service writes the rows


Why Manager A's two chains are sequential and B's two steps are not:
  A2's prompt needs A1's hashtag pool injected into it, so A1 must finish first.
  B1 and B2 feed the same chain but neither needs the other, so they overlap.
"""

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from app.agents.post_generation.post_manager import generate_posts
from app.agents.post_generation.review_manager import generate_reviews
from app.errors import UpstreamServiceError

logger = logging.getLogger("app")

_MAX_ATTEMPTS = 3
_RETRY_DELAY_SECONDS = 1.5


@dataclass
class ManagerResult:
    """What one manager produced, or why it didn't.

    `items` empty with `error` set is the failure case. Both managers report
    independently, which is what lets a dead reviews page leave eight good posts
    untouched instead of failing the whole run.
    """

    items: List[Dict] = field(default_factory=list)
    hashtag_pool: Optional[str] = None
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return bool(self.items)


@dataclass
class GenerationOutcome:
    posts: ManagerResult
    reviews: ManagerResult
    # Reels come out of the SAME call as the posts, so they share the post
    # manager's success or failure. They are a separate result only so the
    # service can write them to their own table.
    reels: List[Dict] = field(default_factory=list)
    scraped_markdown: Optional[str] = None

    @property
    def total_failure(self) -> bool:
        return not self.posts.ok and not self.reviews.ok

    @property
    def error_message(self) -> Optional[str]:
        messages = [m for m in (self.posts.error, self.reviews.error) if m]
        return "\n".join(messages) or None


def _with_retry(func, *args):
    """Retries a flaky model call before giving up, same as ad_angle_service:
    transient network blips to the model APIs have been seen in this environment
    and succeed on a retry."""
    import time

    last_exc: Exception = RuntimeError("_with_retry called with zero attempts")
    for attempt in range(_MAX_ATTEMPTS):
        try:
            return func(*args)
        except UpstreamServiceError:
            # A missing key, an empty reviews page or a refusal will not fix
            # itself on a retry, and retrying wastes the user's time.
            raise
        except Exception as exc:
            last_exc = exc
            if attempt < _MAX_ATTEMPTS - 1:
                time.sleep(_RETRY_DELAY_SECONDS)
    raise last_exc


def _message_of(exc: Exception) -> str:
    """Prefer our own user-facing wording over a raw exception string."""
    return str(getattr(exc, "message", None) or exc)


def run_managers(request) -> GenerationOutcome:
    """Runs Manager A and Manager B concurrently and collects both results.

    Never raises for a single manager failing — that is recorded on its
    ManagerResult. The caller decides what a total failure means.
    """
    with ThreadPoolExecutor(max_workers=2) as pool:
        posts_future = pool.submit(_with_retry, generate_posts, request)
        reviews_future = pool.submit(_with_retry, generate_reviews, request)

        posts = ManagerResult()
        reviews = ManagerResult()
        reels: List[Dict] = []
        scraped: Optional[str] = None

        try:
            items, reels, pool_text = posts_future.result()
            posts = ManagerResult(items=items, hashtag_pool=pool_text)
        except Exception as exc:
            posts = ManagerResult(error=_message_of(exc))
            logger.exception("post_manager_failed request_id=%s", request.id)

        try:
            items, pool_text, scraped = reviews_future.result()
            reviews = ManagerResult(items=items, hashtag_pool=pool_text)
        except Exception as exc:
            reviews = ManagerResult(error=_message_of(exc))
            logger.exception("review_manager_failed request_id=%s", request.id)

    logger.info(
        "generation_done request_id=%s posts=%s reels=%s reviews=%s",
        request.id,
        len(posts.items),
        len(reels),
        len(reviews.items),
    )
    return GenerationOutcome(
        posts=posts, reviews=reviews, reels=reels, scraped_markdown=scraped
    )
