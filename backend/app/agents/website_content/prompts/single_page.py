"""Directives that narrow a bundled page agent to exactly one page.

`service`, `service_area` and `other` each write every page of their kind in one
reply. That is what makes their cross-page uniqueness rule work, because the
model can see its own siblings, and it is also what stops the run being
parallelised: three prompts do the work of nineteen pages while three workers
sit idle.

These directives narrow one of those agents to a single page so each page can be
its own concurrent task, and hand it the siblings it can no longer see so the
uniqueness rule still has something to bite on.

Nothing in the page prompt modules is modified. The client signed off on those
and the bundled path has to stay byte identical, so this is appended after them
instead, which is the same mechanism DIRECT_RESPONSE_DOCTRINE already uses: last
instruction wins any contradiction with the older wording above it. When the
directive is not appended, the agent behaves exactly as it does today.

Two things have to move together for a bundled page: the directive here, and the
prompt variable holding its list of subjects. LIST_VARIABLE_BY_PAGE is the
second. Adding a page to the planner without adding both is a silent, total
failure rather than a partial one, so the planner asserts the sets match at
import.
"""

from typing import List


def _directive(noun: str, plural: str, bundled_by: str) -> str:
    """Builds a single page directive for one kind of bundled page.

    Parametrised rather than written twice, and built from parameters rather
    than by string-replacing one variant into the other: the two directives
    differ only in a noun, and a chain of .replace() calls over prose is the
    kind of thing that silently stops matching when a sentence is reworded.
    """
    return f"""

## THIS REPLY IS ONE PAGE ONLY (OVERRIDES THE INSTRUCTIONS ABOVE)

Everything above tells you to write a page for {bundled_by}. For this reply, do
not. You are writing exactly one page, for one {noun}, and the rest of the
sitemap is context only.

The {noun} you are writing: {{single_subject}}

Rules for this reply, which replace the corresponding rules above:

1. Output ONE page. One H1, one of every block the template calls for, nothing
   repeated for a second {noun}.
2. Do not write, mention, summarise or link the other {plural} as pages. They
   exist, and naming one in passing where it genuinely helps the reader is fine,
   but this page is about the {noun} named above and nothing else.
3. Ignore any instruction above that counts pages, orders pages, or asks you to
   read pages side by side. There is one page here to read.
4. The word target above is per page. It applies to this page.

## WHAT THE OTHER PAGES ALREADY SAY

You cannot see the other {noun} pages, because they are being written at the
same time as this one. Here is what they have opened with, so you do not repeat
it:

{{sibling_openings}}

Do not reuse any sentence, H1, or hero line listed above. Do not reuse its
structure with the nouns swapped either, which is the failure this list exists
to catch: "Fast, reliable gutter repairs across Essex" and "Fast, reliable roof
repairs across Essex" are the same sentence.

This does NOT apply to the blocks the instructions above allow to be consistent
sitewide. The trust bar, the Why Choose Us block, the Areas We Cover block and
the call to action are meant to be identical on every page. Leave them
identical. Do not invent a variant of the call to action to satisfy this
section: a call to action that changes per page is a worse outcome than a
repeated one, and it is the specific mistake this paragraph exists to prevent.
"""


#: Appended when one service page is written on its own. Undoes three things
#: that are explicit in the prompt above it: "Create SEPARATE content for EACH
#: service listed under SERVICES in the sitemap", the numbered "Create ONE
#: complete page for EACH service", and the CROSS-PAGE UNIQUENESS block, which
#: assumes the siblings are in front of it.
SINGLE_SERVICE_DIRECTIVE = _directive(
    "service", "services", "each service in the sitemap"
)

#: The service area equivalent, which bundles by area rather than by service.
SINGLE_AREA_DIRECTIVE = _directive("area", "areas", "each area covered")

#: And the other pages agent, which bundles by page name: Our Process, Meet The
#: Team, FAQs and whatever else the sitemap lists. It needed a directive for the
#: same reason the other two did, and finding that out the hard way is instructive:
#: without one, the planner still split it into eight tasks and each task ran the
#: unmodified bundled prompt, so all eight wrote all eight pages. Eight times the
#: cost for one page group, and the duplication is total rather than incidental.
SINGLE_OTHER_DIRECTIVE = _directive("page", "pages", "each page listed under other pages")

#: Which directive goes with which bundled page key, so the planner does not
#: carry the mapping. A key MISSING from here while present in the planner's own
#: bundled list is the bug described above, so the two are asserted equal by
#: tests rather than kept in step by hand.
DIRECTIVE_BY_PAGE = {
    "service": SINGLE_SERVICE_DIRECTIVE,
    "service_area": SINGLE_AREA_DIRECTIVE,
    "other": SINGLE_OTHER_DIRECTIVE,
}

#: The prompt variable each bundled agent reads its list of subjects from.
#:
#: Narrowing this to the one subject is half of what makes a single page reply
#: work; the directive is the other half. Appending the directive alone leaves
#: the model holding a full list it was just told to cover, and then the two
#: instructions disagree.
LIST_VARIABLE_BY_PAGE = {
    "service": "services",
    "service_area": "areas",
    "other": "other_pages",
}


def format_siblings(openings: List[str]) -> str:
    """Renders the sibling list for the directive.

    Empty means this is the first page to finish, or the only one. Saying so
    explicitly matters: an empty bullet list reads as a formatting failure and
    the model tries to fill it in.
    """
    lines = [line.strip() for line in openings if line and line.strip()]
    if not lines:
        return (
            "Nothing yet. This is the first of these pages to be written, so "
            "there is nothing to avoid. Write it as well as you can and the "
            "later pages will avoid you."
        )
    return "\n".join(f"- {line}" for line in lines)
