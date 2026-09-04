"""Tests for the content run orchestration: the executor, the split and dedupe.

Nothing here calls a model. The three things worth guarding are all pure:

  the executor    concurrency, failure isolation, and that an empty reply is a
                  failure rather than an empty asset
  the split       every bundled page agent has a directive AND a list variable,
                  which is the pair whose absence caused a real bug: eight tasks
                  each running the unmodified bundled prompt and writing all
                  eight pages
  the dedupe      the find stage, which is deliberately deterministic so that
                  the sitewide blocks are excluded before a model sees them

Run: backend/venv/Scripts/python.exe tests/test_content_run.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agents.website_content.prompts.single_page import (
    DIRECTIVE_BY_PAGE,
    LIST_VARIABLE_BY_PAGE,
    format_siblings,
)
from app.services.content_run.dedupe import find_duplicates
from app.services.content_run.planners.website import _BUNDLED
from app.services.content_run.tasks import Task, run_tasks


# --------------------------------------------------------------------------
# The bundled page contract
# --------------------------------------------------------------------------


def test_every_bundled_page_has_a_directive():
    """The bug this exists for cost eight page calls and produced eight copies.

    `other` was in the planner's bundled list and not in DIRECTIVE_BY_PAGE, so
    `write_single_page` fell through to the ordinary path and ignored the
    subject. Each of the eight tasks ran the full bundled prompt and wrote all
    eight pages. Nothing raised, nothing logged, and the output looked plausible
    until you noticed every card held the same text.
    """
    assert set(_BUNDLED) == set(DIRECTIVE_BY_PAGE)


def test_every_bundled_page_has_a_list_variable():
    """The directive alone is not enough.

    Without narrowing the prompt's own list variable the model is handed a full
    list it was just told to cover, and the two instructions disagree.
    """
    assert set(_BUNDLED) == set(LIST_VARIABLE_BY_PAGE)


def test_directives_carry_both_template_placeholders():
    """A missing placeholder is a KeyError at generation time, not at import."""
    for page, directive in DIRECTIVE_BY_PAGE.items():
        assert "{single_subject}" in directive, page
        assert "{sibling_openings}" in directive, page


def test_directives_keep_the_cta_exemption():
    """The exemption that stops the dedupe pass breaking the sitewide CTA.

    Without it the model bends the one sitewide call to action into a per page
    variant to satisfy the uniqueness instruction, which has happened before.
    """
    for page, directive in DIRECTIVE_BY_PAGE.items():
        assert "call to action" in directive, page
        assert "identical" in directive, page


def test_format_siblings_says_so_when_empty():
    """An empty bullet list reads as a formatting failure and gets filled in."""
    assert "Nothing yet" in format_siblings([])
    assert format_siblings(["  "]) == format_siblings([])
    assert format_siblings(["One", "Two"]) == "- One\n- Two"


# --------------------------------------------------------------------------
# The executor
# --------------------------------------------------------------------------


def test_tasks_run_concurrently():
    """Six quarter-second tasks over three workers is a half second, not 1.5."""
    tasks = [
        Task(key=f"k{i}", section="pages", position=i, title=f"t{i}",
             run=lambda: (time.sleep(0.25), "body")[1])
        for i in range(6)
    ]
    started = time.monotonic()
    results = run_tasks(tasks, max_workers=3)
    elapsed = time.monotonic() - started

    assert all(r.ok for r in results)
    assert elapsed < 1.0, f"took {elapsed:.2f}s, so it did not run concurrently"


def test_one_failure_does_not_affect_the_others():
    """A run where two of eight failed keeps the six, and says which failed."""

    def boom():
        raise RuntimeError("upstream said no")

    tasks = [
        Task(key="good", section="pages", position=0, title="good", run=lambda: "body"),
        Task(key="bad", section="pages", position=1, title="bad", run=boom),
        Task(key="empty", section="pages", position=2, title="empty", run=lambda: "   "),
    ]
    results = {r.task.key: r for r in run_tasks(tasks)}

    assert results["good"].ok
    assert not results["bad"].ok
    assert "upstream said no" in results["bad"].error
    # An empty reply is a failure, not an empty asset. Storing it would put a
    # blank card in front of someone with nothing to say why.
    assert not results["empty"].ok


def test_on_result_fires_for_every_task_including_failures():
    """The caller persists from on_result, so a skipped call is a lost asset."""
    seen = []
    tasks = [
        Task(key="a", section="pages", position=0, title="a", run=lambda: "x"),
        Task(key="b", section="pages", position=1, title="b",
             run=lambda: (_ for _ in ()).throw(RuntimeError("no"))),
    ]
    run_tasks(tasks, on_result=lambda r: seen.append(r.task.key))
    assert sorted(seen) == ["a", "b"]


def test_a_persist_failure_does_not_abandon_the_run():
    """One asset failing to save must not cost the rest of the run."""
    calls = []

    def explode(result):
        calls.append(result.task.key)
        raise RuntimeError("database went away")

    tasks = [
        Task(key=f"k{i}", section="pages", position=i, title="t", run=lambda: "body")
        for i in range(4)
    ]
    results = run_tasks(tasks, on_result=explode)
    assert len(results) == 4
    assert len(calls) == 4


def test_no_tasks_is_not_an_error():
    assert run_tasks([]) == []


# --------------------------------------------------------------------------
# The dedupe find stage
# --------------------------------------------------------------------------


def _page(h1: str, hero: str) -> str:
    return f"""# {h1}
{hero}

## Why Choose Us
We are Which Trusted Traders and we answer the phone every time.

## Areas We Cover
Chelmsford, Colchester, Cambridge, Brentwood and Saffron Walden.

## Ready to get started
Tell us about your project and we will come out and take a look."""


def test_repeated_h1_is_found():
    pages = {
        "a": _page("Fast, reliable roof repairs across Essex", "Your roof is leaking today."),
        "b": _page("Fast, reliable roof repairs across Essex", "Water is down the wall today."),
    }
    found = find_duplicates(pages)
    assert list(found) == ["b"], "the first page to use a sentence should keep it"
    assert any("Fast, reliable roof repairs" in s for s in found["b"])


def test_sitewide_blocks_are_never_flagged():
    """The trust bar, Why Choose Us, Areas We Cover and the CTA repeat by design.

    This is the whole reason the find stage is Python and not a model. A model
    asked whether these pages are too similar finds these blocks first, because
    they are the most repeated text on the site and they are supposed to be.
    """
    pages = {"a": _page("Roof repairs in Essex", "One."), "b": _page("Gutter work in Essex", "Two.")}
    found = find_duplicates(pages)
    flagged = [s for sentences in found.values() for s in sentences]
    for allowed in ("Which Trusted Traders", "Chelmsford", "Tell us about your project"):
        assert not any(allowed in s for s in flagged), f"{allowed!r} should be exempt"


def test_near_misses_collide():
    """The failure being caught is the same sentence with a noun swapped."""
    pages = {
        "a": _page("Roof repairs", "We fix leaking roofs across the whole of Essex."),
        "b": _page("Gutter work", "we fix leaking roofs across the whole of essex!"),
    }
    assert "b" in find_duplicates(pages)


def test_short_sentences_are_not_duplication():
    '''"Get in touch." on nine pages is English, not a finding.'''
    pages = {"a": "# One\n\nGet in touch.", "b": "# Two\n\nGet in touch."}
    assert find_duplicates(pages) == {}


def test_a_single_page_has_nothing_to_compare():
    assert find_duplicates({"a": _page("Roof repairs", "One.")}) == {}


# --------------------------------------------------------------------------
# Runner. Plain script rather than pytest, matching the other test modules
# here, so it needs nothing installed beyond what the app already needs.
# --------------------------------------------------------------------------


def main() -> int:
    cases = [
        (name, fn)
        for name, fn in sorted(globals().items())
        if name.startswith("test_") and callable(fn)
    ]
    failures = 0
    for name, fn in cases:
        try:
            fn()
        except AssertionError as exc:
            failures += 1
            print("FAIL  %s" % name)
            print("        %s" % (exc or "assertion failed"))
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print("ERROR %s" % name)
            print("        %s: %s" % (type(exc).__name__, exc))

    if failures:
        print("")
        print("FAIL  %d of %d checks failed" % (failures, len(cases)))
        return 1
    print("OK    %d checks passed" % len(cases))
    return 0


if __name__ == "__main__":
    sys.exit(main())
