"""The task model and the executor every content type shares.

One shape, three phases:

    prepare   one call that every item then depends on. The website brief, the
              social hashtag pool, the blog metadata. Sequential by necessity,
              because the fan-out has nothing to fan out without it.
    fan out   one Task per item, run concurrently. This is the phase the run
              spends almost all of its wall clock in.
    reconcile one call that sees every result together. Optional, and only
              website uses it today, to keep the cross-page uniqueness
              guarantee that splitting the service pages would otherwise lose.

Nothing here knows what a reel or a service page is. The per content type
planners in `planners/` supply the three phases; this module runs them, records
what happened, and never raises out of a worker.

Why a shared executor rather than each planner spawning its own pool: the
concurrency limit that matters is on the Anthropic account, not on the content
type. Three separate pools of three are nine concurrent calls, which is how a
run starts getting rate limited half way through and returns `partial` for
reasons that have nothing to do with the copy.
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

#: How many item agents run at once, across the whole run.
#:
#: Three, matching what the three existing pipelines each already use
#: (website MAX_CONCURRENT_SECTIONS, blog MAX_CONCURRENT_BLOGS,
#: post hero images _MAX_CONCURRENT_IMAGE_CALLS is 4). Those limits were arrived
#: at against the same Anthropic account this runs on, so raising it here
#: without raising them there would just move the rate limiting around.
MAX_CONCURRENT_ITEMS = 3


@dataclass(frozen=True)
class Task:
    """One item to generate: one page, one reel, one blog, one ad angle.

    `section` and `position` are written straight onto the asset row, so a task
    carries its own destination and results can be persisted in whatever order
    they finish.

    `run` is called on a worker thread and MUST NOT touch a Session. Everything
    it needs comes from `payload`, which the planner filled in on the thread
    that owned the Session. This is the same rule `RequestSnapshot` exists to
    enforce in the website pipeline, for the same reason.
    """

    key: str
    section: str
    position: int
    title: str
    run: Callable[[], str]
    payload: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TaskResult:
    """What one task produced, or why it did not. Never carries an exception."""

    task: Task
    body: Optional[str] = None
    error: Optional[str] = None
    seconds: float = 0.0

    @property
    def ok(self) -> bool:
        return self.error is None and bool(self.body)


def _message_of(exc: Exception) -> str:
    """A short reason for a failed task, safe to store and show.

    Deliberately not the whole traceback: this string lands on an asset row and
    is read by whoever is looking at the run, so it has to be a sentence rather
    than a stack.
    """
    text = str(exc).strip() or exc.__class__.__name__
    return text if len(text) <= 300 else text[:297] + "..."


def run_tasks(
    tasks: List[Task],
    on_result: Optional[Callable[[TaskResult], None]] = None,
    max_workers: int = MAX_CONCURRENT_ITEMS,
) -> List[TaskResult]:
    """Runs every task concurrently. Never raises.

    `on_result` is called with each result as it lands, on THIS thread rather
    than the worker that produced it. That is what lets the caller persist with
    its own Session without sharing it across threads, and it means a finished
    item is on the page the moment it is done rather than when the slowest
    sibling finishes.

    Ordered by completion, not submission. Order carries no meaning because
    every result carries its own task, and therefore its own section and
    position.

    One task failing never affects another: the failure is recorded on that
    result and the rest of the run continues. A run where two of twelve posts
    failed is `partial`, which is a state the operator can act on, rather than
    `failed`, which throws away ten good posts.
    """
    if not tasks:
        return []

    results: List[TaskResult] = []

    def _guarded(task: Task) -> TaskResult:
        started = time.monotonic()
        try:
            body = task.run()
        except Exception as exc:  # noqa: BLE001 - a worker must never raise out
            logger.exception("content_task_failed key=%s", task.key)
            return TaskResult(
                task=task, error=_message_of(exc), seconds=time.monotonic() - started
            )
        elapsed = time.monotonic() - started
        if not (body or "").strip():
            # An empty body is a failure, not an empty asset. Storing it would
            # put a blank card in front of someone with nothing to say why.
            return TaskResult(
                task=task, error="The agent returned nothing.", seconds=elapsed
            )
        return TaskResult(task=task, body=body, seconds=elapsed)

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures: List[Future] = [pool.submit(_guarded, task) for task in tasks]
        for future in as_completed(futures):
            result = future.result()  # _guarded never raises
            results.append(result)
            if on_result is not None:
                try:
                    on_result(result)
                except Exception:
                    # A persistence failure for one item must not abandon the
                    # rest of the run. The item is left without its row and the
                    # log carries the reason; the run ends `partial`.
                    logger.exception(
                        "content_task_persist_failed key=%s", result.task.key
                    )

    ok = sum(1 for r in results if r.ok)
    logger.info(
        "content_tasks_done total=%s ok=%s failed=%s slowest=%.1fs",
        len(results),
        ok,
        len(results) - ok,
        max((r.seconds for r in results), default=0.0),
    )
    return results


@dataclass
class Plan:
    """What a planner hands back: the tasks, and how to reconcile them.

    `reconcile` sees every successful result together and may rewrite bodies. It
    returns the bodies it changed, keyed by task key, so a planner that changes
    nothing returns an empty dict and the caller does no extra writes.

    It runs on the caller thread after the fan-out, so it may be slow but must
    not be endless: it is one call, not a loop over items.
    """

    tasks: List[Task] = field(default_factory=list)
    reconcile: Optional[Callable[[List[TaskResult]], Dict[str, str]]] = None
    #: Anything the planner wants recorded on the run, merged into `source`
    #: under `prepared`. The website brief goes here, so a re-run or a later
    #: single-item regeneration does not have to rebuild it.
    prepared: Dict[str, Any] = field(default_factory=dict)
    #: Set when preparation failed outright, in which case `tasks` is empty and
    #: the run is `failed` with this as its summary.
    error: Optional[str] = None
