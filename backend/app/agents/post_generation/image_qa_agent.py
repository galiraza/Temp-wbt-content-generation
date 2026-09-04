"""Orchestrates the classical-CV stretch checks in app.services.image_qa
against one finished post image, mapping which known value backs which
element check. Sibling to the not-yet-built final-image generation agent,
the same relationship post_manager.py/review_manager.py have to client.py.

This replaces the n8n workflow's vision-LLM QA agent for the two checks that
have a genuine ground truth to verify against (the logo, the hero photo) and
approximates three more with heuristics (headline, subheadline, CTA text/
pill) - it does NOT replace the sixth check (the hero photo's mask/frame
shape), which has no reliable classical-CV technique without variant-level
target-shape data that doesn't exist yet. See image_qa.py's module docstring
and each function's docstring for what confidence each check actually has.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from app.services.image_qa import (
    check_pill_shape,
    check_round_letter_ratios,
    check_uniform_scale,
    locate_text_line,
)

_DEFAULT_MAX_DISTORTION_RATIO = 1.10


@dataclass
class ElementCheck:
    name: str  # "logo" | "hero_photo" | "headline" | "subheadline" | "cta_text" | "cta_pill"
    status: str  # "pass" | "flagged" | "inconclusive" | "not_checked"
    detail: dict = field(default_factory=dict)


@dataclass
class QaReport:
    checks: List[ElementCheck]

    @property
    def any_flagged(self) -> bool:
        return any(c.status == "flagged" for c in self.checks)


def _scale_check(name: str, reference_path: Path, composite_path: Path) -> ElementCheck:
    result = check_uniform_scale(reference_path, composite_path)
    if not result.found:
        return ElementCheck(name, "inconclusive", {"reason": "not enough matched features"})

    detail = {
        "distortion_ratio": result.distortion_ratio,
        "scale_x": result.scale_x,
        "scale_y": result.scale_y,
        "method": result.method,
        "inlier_count": result.inlier_count,
    }
    if result.distortion_ratio > _DEFAULT_MAX_DISTORTION_RATIO:
        return ElementCheck(name, "flagged", detail)
    if result.method == "template":
        # The template fallback only ever searches isotropic scales, so it
        # is STRUCTURALLY incapable of detecting non-uniform stretch - a
        # "pass" from it means "found, at some uniform scale", never "this
        # is verified undistorted". Reporting it as a confident pass would
        # be actively misleading (a false negative dressed up as a verdict)
        # for exactly the case this check exists to catch, so this stays
        # inconclusive even though something was found.
        detail["reason"] = "only matched via isotropic template search - cannot rule out non-uniform stretch"
        return ElementCheck(name, "inconclusive", detail)
    return ElementCheck(name, "pass", detail)


_ROUND_LETTER_FLAG_FRACTION = 0.4


def _text_check(name: str, composite_path: Path, expected_text: str) -> ElementCheck:
    if not expected_text or not expected_text.strip():
        return ElementCheck(name, "not_checked", {"reason": "no expected text for this element"})

    line = locate_text_line(composite_path, expected_text)
    if not line.found:
        return ElementCheck(
            name, "inconclusive", {"reason": "could not locate this text in the image", "ocr_similarity": line.similarity}
        )

    letters = check_round_letter_ratios(composite_path, line.bbox, expected_text)
    if not letters.found or letters.checked_count == 0:
        return ElementCheck(name, "inconclusive", {"reason": "glyph count did not line up with expected text"})

    # A single borderline letter is noise (real fonts render round letters at
    # a range of natural ratios, confirmed empirically - a clean baseline
    # sample still flags ~1-2 of 10 letters at the band edge). Genuine
    # non-uniform stretch shows up as MOST checked letters flagged at once,
    # with much more extreme ratios - so flag on a majority, not on "any".
    flagged_fraction = len(letters.flagged_ratios) / letters.checked_count
    status = "flagged" if flagged_fraction >= _ROUND_LETTER_FLAG_FRACTION else "pass"
    return ElementCheck(
        name,
        status,
        {
            "flagged_ratios": letters.flagged_ratios,
            "checked_count": letters.checked_count,
            "flagged_fraction": flagged_fraction,
        },
    )


def _pill_check(composite_path: Path, primary_hex: str) -> ElementCheck:
    result = check_pill_shape(composite_path, primary_hex)
    if not result.found:
        return ElementCheck("cta_pill", "inconclusive", {"reason": "could not locate a region matching primary_hex"})
    status = "pass" if result.is_stadium_shape else "flagged"
    return ElementCheck(
        "cta_pill", status, {"fill_ratio": result.fill_ratio, "expected_fill_ratio": result.expected_fill_ratio}
    )


def run_qa(
    composite_path: Path,
    *,
    logo_path: Path,
    hero_photo_path: Path,
    headline: str,
    subheadline: str,
    cta_text: str,
    primary_hex: str,
) -> QaReport:
    """Runs every check this module can do for one finished post image.
    Deliberately produces no check for the hero photo's mask/frame shape -
    see module docstring - that element's ElementCheck.status is always
    "not_checked", not a fake pass.
    """
    checks = [
        _scale_check("logo", logo_path, composite_path),
        _scale_check("hero_photo", hero_photo_path, composite_path),
        _text_check("headline", composite_path, headline),
        _text_check("subheadline", composite_path, subheadline),
        _text_check("cta_text", composite_path, cta_text),
        _pill_check(composite_path, primary_hex),
        ElementCheck(
            "hero_photo_frame",
            "not_checked",
            {"reason": "no reliable classical-CV technique without a known target shape per layout variant"},
        ),
    ]
    return QaReport(checks=checks)
