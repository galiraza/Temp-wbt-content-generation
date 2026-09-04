"""The refinement loop every section goes through: Critic -> Refiner -> Evaluator.

Six identical copies of this loop existed in the workflow, one per section, as
sixty-odd duplicated nodes (`Critic Agent` through `Critic Agent5`, and so on).
They are one function here; nothing about them differed but the branch they sat
on.

    loop_input(draft, turn=1, remaining_issues="")
        |
        v
    Critic Agent      diagnoses AI-writing fingerprints, never rewrites
        |
        v
    Refiner Agent     rewrites to the critic's severity ratings
        |
        v
    Evaluator Agent   PASS or REVISE, plus a carry-forward list
        |
        v
    loop_increment    turn += 1, output = the REFINER's text
        |
        v
    loop_condition    turn > 2 OR pass  ->  done
                      otherwise         ->  back to loop_input

Three details are load-bearing and easy to get wrong:

1. **Two passes, maximum.** `loop_condition` is `turn > 2 OR pass`, and `turn` is
   incremented before the test, so a draft that never passes is refined exactly
   twice. MAX_TURNS is that number.

2. **The refined text wins even on REVISE.** `loop_increment` sets
   `output: $('Refiner Agent').first().json.text` unconditionally. So when the
   second pass still comes back REVISE, the section that ships is the second
   refinement -- not the original draft, and not the first pass. The evaluator's
   verdict decides whether to loop again, not which text to keep.

3. **The critic reads the draft, the refiner rewrites the same draft.** Both take
   `loop_input.output`, so the refiner works from the text the critic actually
   read. On round 2 that is round 1's refinement, carried forward by
   loop_increment.

Every round is returned, not just the last, so the audit trail the workflow threw
away is stored per section.
"""

import logging
from dataclasses import dataclass, field
from typing import List, Optional

from langchain_core.prompts import ChatPromptTemplate

from app.agents.website_content.client import structured_llm, text_llm
from app.agents.website_content.parsers import (
    CarryForwardIssue,
    EvaluatorVerdict,
    format_carry_forward,
)
from app.agents.website_content.retry import with_retry
from app.agents.website_content.prompts.refine_prompts import (
    CRITIC_SYSTEM_PROMPT,
    CRITIC_USER_PROMPT,
    EVALUATOR_SYSTEM_PROMPT,
    EVALUATOR_USER_PROMPT,
    REFINER_SYSTEM_PROMPT,
    REFINER_USER_PROMPT,
)

logger = logging.getLogger("app")

#: `loop_condition`: turn > 2, tested after the increment. Two refinement passes.
MAX_TURNS = 2

_CRITIC_TEMPLATE = ChatPromptTemplate.from_messages(
    [("system", CRITIC_SYSTEM_PROMPT), ("user", CRITIC_USER_PROMPT)]
)
_REFINER_TEMPLATE = ChatPromptTemplate.from_messages(
    [("system", REFINER_SYSTEM_PROMPT), ("user", REFINER_USER_PROMPT)]
)
_EVALUATOR_TEMPLATE = ChatPromptTemplate.from_messages(
    [("system", EVALUATOR_SYSTEM_PROMPT), ("user", EVALUATOR_USER_PROMPT)]
)


@dataclass
class RefinementRound:
    """One Critic -> Refiner -> Evaluator pass over one section."""

    turn: int
    critic_report: str
    refined_content: str
    verdict: str = "REVISE"
    passed: bool = False
    reason: str = ""
    checks: dict = field(default_factory=dict)
    carry_forward: List[CarryForwardIssue] = field(default_factory=list)


@dataclass
class RefinementResult:
    """The final text plus every round that produced it."""

    content: str
    rounds: List[RefinementRound] = field(default_factory=list)
    #: Set when the loop stopped early because a call failed. The content is
    #: still the best text reached, so this is a note rather than a failure.
    error: Optional[str] = None

    @property
    def passed(self) -> bool:
        return bool(self.rounds) and self.rounds[-1].passed

    @property
    def turns(self) -> int:
        return len(self.rounds)


def critique(draft: str, remaining_issues: str, *, label: str) -> str:
    chain = _CRITIC_TEMPLATE | text_llm(label="critic")
    logger.info("website_refine_critic label=%s", label)
    return chain.invoke({"draft": draft, "remaining_issues": remaining_issues})


def refine(draft: str, critic_report: str, *, label: str) -> str:
    chain = _REFINER_TEMPLATE | text_llm(label="refiner")
    logger.info("website_refine_refiner label=%s", label)
    return chain.invoke({"draft": draft, "critic_report": critic_report})


def evaluate(refined_page: str, draft: str, critic_report: str, *, label: str) -> EvaluatorVerdict:
    """The gatekeeper. Bound to EvaluatorVerdict, replacing n8n's output parser."""
    chain = _EVALUATOR_TEMPLATE | structured_llm(EvaluatorVerdict, label="evaluator")
    logger.info("website_refine_evaluator label=%s", label)
    return chain.invoke(
        {"refined_page": refined_page, "draft": draft, "critic_report": critic_report}
    )


def refine_section(draft: str, *, label: str) -> RefinementResult:
    """Runs up to MAX_TURNS refinement passes over one section. Never raises.

    A failed call mid-loop returns everything reached so far. That is the whole
    point of separating this from the writing: by the time the critic runs, a
    full page exists, and losing it because the third of six model calls timed
    out would be the worst possible trade.
    """
    current = draft
    remaining_issues = ""
    rounds: List[RefinementRound] = []

    for turn in range(1, MAX_TURNS + 1):
        try:
            # Each call retries on its own: a dropped connection to the model
            # took out two sections' loops simultaneously in a live run, and
            # losing a written page to one network blip is the worst trade here.
            report = with_retry(critique, current, remaining_issues, label=f"{label}-t{turn}")
            refined = with_retry(refine, current, report, label=f"{label}-t{turn}")
            verdict = with_retry(evaluate, refined, current, report, label=f"{label}-t{turn}")
        except Exception as exc:
            message = str(getattr(exc, "message", None) or exc)
            logger.warning(
                "website_refine_failed label=%s turn=%s error=%s", label, turn, message
            )
            return RefinementResult(content=current, rounds=rounds, error=message)

        rounds.append(
            RefinementRound(
                turn=turn,
                critic_report=report,
                refined_content=refined,
                verdict=verdict.verdict,
                passed=verdict.passed,
                reason=verdict.reason,
                checks=verdict.checks.model_dump(),
                carry_forward=list(verdict.carry_forward),
            )
        )

        # `loop_increment`: the refiner's text is carried forward whatever the
        # verdict says. See the module docstring, point 2.
        current = refined

        if verdict.passed:
            logger.info("website_refine_passed label=%s turn=%s", label, turn)
            break

        remaining_issues = format_carry_forward(verdict.carry_forward)

    if rounds and not rounds[-1].passed:
        logger.info(
            "website_refine_exhausted label=%s turns=%s reason=%.120s",
            label,
            len(rounds),
            rounds[-1].reason,
        )
    return RefinementResult(content=current, rounds=rounds)
