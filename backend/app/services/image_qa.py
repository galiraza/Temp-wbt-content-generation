"""Deterministic, non-LLM checks for non-uniform (disproportionate) stretch
in a finished branded post image - a classical-CV replacement for the n8n
workflow's vision-LLM QA agent, for the subset of checks that actually have
a ground truth to verify against.

Two different techniques for two different situations:
  - check_uniform_scale: for an element with a KNOWN SOURCE IMAGE (the logo,
    the hero photo) - feature-match the source against the finished
    composite and recover the real geometric transform between them, then
    read the x/y scale factors directly off it. This is precise.
  - locate_text_line / check_round_letter_ratios / check_pill_shape: for
    elements with a known EXPECTED STRING or COLOR but no source image (the
    headline, subheadline, CTA text and its pill) - these are heuristics
    that catch obvious distortion and are explicitly NOT as reliable as the
    scale-transform check above. See each function's docstring for its
    honest ceiling.

Every function returns found=False (never a guessed answer) when it can't
get a confident read - a missing verdict must never be mistaken for a pass.
"""

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np
import pytesseract
from pytesseract import Output

# --- Check 1 & 4: logo / hero photo scale, via feature matching ---------------

_ORB_FEATURES = 2000
_LOWE_RATIO = 0.75
_MIN_MATCHES_FOR_AFFINE = 4  # cv2.estimateAffine2D's hard minimum


@dataclass
class ScaleCheckResult:
    found: bool
    scale_x: Optional[float] = None
    scale_y: Optional[float] = None
    distortion_ratio: Optional[float] = None  # None when found=False - never a fake 1.0
    inlier_count: int = 0
    method: str = ""  # "orb" | "sift" | "template" | ""


def _foreground_bbox_crop(image: np.ndarray) -> np.ndarray:
    """If the reference has an alpha channel, crop to its non-transparent
    bounding box first - otherwise the reference's own (often white/blank)
    background hurts correlation against a differently-colored composite
    background it was never actually placed on unchanged."""
    if image.shape[2] < 4:
        return image[:, :, :3]
    alpha = image[:, :, 3]
    ys, xs = np.where(alpha > 10)
    if len(xs) == 0:
        return image[:, :, :3]
    x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
    return image[y0:y1, x0:x1, :3]


def _match_and_estimate(
    reference_gray: np.ndarray, composite_gray: np.ndarray, detector, method: str
) -> Optional[ScaleCheckResult]:
    kp1, des1 = detector.detectAndCompute(reference_gray, None)
    kp2, des2 = detector.detectAndCompute(composite_gray, None)
    if des1 is None or des2 is None or len(kp1) < _MIN_MATCHES_FOR_AFFINE or len(kp2) < _MIN_MATCHES_FOR_AFFINE:
        return None

    norm = cv2.NORM_HAMMING if method == "orb" else cv2.NORM_L2
    matcher = cv2.BFMatcher(norm)
    raw_matches = matcher.knnMatch(des1, des2, k=2)
    good = [m for m, n in raw_matches if len(raw_matches) and m.distance < _LOWE_RATIO * n.distance]
    if len(good) < _MIN_MATCHES_FOR_AFFINE:
        return None

    src_pts = np.float32([kp1[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
    dst_pts = np.float32([kp2[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)

    affine, inlier_mask = cv2.estimateAffine2D(src_pts, dst_pts, method=cv2.RANSAC)
    if affine is None:
        return None

    linear_part = affine[:, :2]
    singular_values = np.linalg.svd(linear_part, compute_uv=False)
    sx, sy = float(singular_values[0]), float(singular_values[1])
    if sx <= 0 or sy <= 0:
        return None
    distortion_ratio = max(sx, sy) / min(sx, sy)
    inlier_count = int(inlier_mask.sum()) if inlier_mask is not None else len(good)

    return ScaleCheckResult(
        found=True,
        scale_x=sx,
        scale_y=sy,
        distortion_ratio=distortion_ratio,
        inlier_count=inlier_count,
        method=method,
    )


def _template_match_fallback(reference_bgr: np.ndarray, composite_bgr: np.ndarray) -> Optional[ScaleCheckResult]:
    """Coarser fallback for a logo with too little internal detail for
    feature matching (it's never cropped, only resized/repositioned, so a
    whole-template search is workable here even though it wouldn't be for
    the hero photo). Only yields a bounding-box aspect-ratio comparison, not
    a clean scale decomposition - lower confidence than orb/sift, hence its
    own `method` value."""
    ref_gray = cv2.cvtColor(reference_bgr, cv2.COLOR_BGR2GRAY)
    comp_gray = cv2.cvtColor(composite_bgr, cv2.COLOR_BGR2GRAY)
    ref_h, ref_w = ref_gray.shape
    ref_ratio = ref_w / ref_h

    best_score, best_scale = -1.0, None
    for scale in np.linspace(0.1, 2.0, 40):
        w, h = round(ref_w * scale), round(ref_h * scale)
        if w < 8 or h < 8 or w > comp_gray.shape[1] or h > comp_gray.shape[0]:
            continue
        resized = cv2.resize(ref_gray, (w, h))
        result = cv2.matchTemplate(comp_gray, resized, cv2.TM_CCOEFF_NORMED)
        _, score, _, _ = cv2.minMaxLoc(result)
        if score > best_score:
            best_score, best_scale = score, scale

    if best_scale is None or best_score < 0.5:
        return None

    # A uniformly-scaled match by definition has scale_x == scale_y here,
    # since only isotropic scale was searched - this fallback can only ever
    # confirm "found, and it happens to look uniform", never detect
    # non-uniform stretch. Reported at distortion_ratio=1.0 accordingly, and
    # callers should weight this method lower than orb/sift.
    return ScaleCheckResult(
        found=True, scale_x=best_scale, scale_y=best_scale, distortion_ratio=1.0,
        inlier_count=0, method="template",
    )


def check_uniform_scale(
    reference_path: Path,
    composite_path: Path,
    *,
    max_distortion_ratio: float = 1.10,
    min_inliers: int = 8,
) -> ScaleCheckResult:
    """Was this element (logo or hero photo) scaled by the same factor on
    both axes when it was placed into the composite?

    ORB first (fast, license-free, usually sufficient), SIFT second (more
    keypoints on flatter/simpler images), multi-scale template matching
    last (logo only - coarser, no real scale decomposition). Returns
    found=False rather than guessing when nothing clears min_inliers -
    typically a very flat/minimal logo with too few distinctive features.
    """
    reference = cv2.imread(str(reference_path), cv2.IMREAD_UNCHANGED)
    composite = cv2.imread(str(composite_path), cv2.IMREAD_UNCHANGED)
    if reference is None or composite is None:
        return ScaleCheckResult(found=False)

    reference = _foreground_bbox_crop(reference) if reference.ndim == 3 and reference.shape[2] >= 3 else reference
    composite_bgr = composite[:, :, :3] if composite.ndim == 3 and composite.shape[2] >= 4 else composite

    ref_gray = cv2.cvtColor(reference, cv2.COLOR_BGR2GRAY)
    comp_gray = cv2.cvtColor(composite_bgr, cv2.COLOR_BGR2GRAY)

    for method, detector in (("orb", cv2.ORB_create(_ORB_FEATURES)), ("sift", cv2.SIFT_create())):
        result = _match_and_estimate(ref_gray, comp_gray, detector, method)
        if result is not None and result.inlier_count >= min_inliers:
            return result

    template_result = _template_match_fallback(reference, composite_bgr)
    if template_result is not None:
        return template_result

    return ScaleCheckResult(found=False)


# --- Checks 2, 3, 6a: headline / subheadline / CTA text letterforms -----------

_ROUND_LETTERS = set("oOcCeEaA")
_PLAUSIBLE_RATIO_BAND = (0.75, 1.05)
_CONTOUR_MIN_AREA = 6  # px^2 - drops speckle noise from thresholding


@dataclass
class TextLineResult:
    found: bool
    bbox: Optional[Tuple[int, int, int, int]] = None  # (x, y, w, h)
    matched_text: str = ""
    similarity: float = 0.0


def locate_text_line(composite_path: Path, expected_text: str) -> TextLineResult:
    """Finds where a known text string was rendered, trusting Tesseract's
    LOCATION only - not its character recognition, which is unreliable on a
    large bold geometric-sans display headline (a very different input from
    the printed-document text Tesseract is tuned for). Groups words into
    lines via Tesseract's own line grouping, then fuzzy-matches each line's
    recognized text against expected_text (stdlib difflib) to find which
    line IS this element.
    """
    if not expected_text or not expected_text.strip():
        return TextLineResult(found=False)

    import difflib

    image = cv2.imread(str(composite_path))
    if image is None:
        return TextLineResult(found=False)

    data = pytesseract.image_to_data(image, output_type=Output.DICT)
    lines: dict = {}
    for i, text in enumerate(data["text"]):
        if not text.strip():
            continue
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        lines.setdefault(key, []).append(i)

    best_ratio, best_bbox, best_text = 0.0, None, ""
    for indices in lines.values():
        line_text = " ".join(data["text"][i] for i in indices)
        ratio = difflib.SequenceMatcher(None, line_text.lower(), expected_text.lower()).ratio()
        if ratio > best_ratio:
            xs = [data["left"][i] for i in indices]
            ys = [data["top"][i] for i in indices]
            ws = [data["left"][i] + data["width"][i] for i in indices]
            hs = [data["top"][i] + data["height"][i] for i in indices]
            best_ratio = ratio
            best_bbox = (min(xs), min(ys), max(ws) - min(xs), max(hs) - min(ys))
            best_text = line_text

    if best_bbox is None or best_ratio < 0.3:
        return TextLineResult(found=False, matched_text=best_text, similarity=best_ratio)
    return TextLineResult(found=True, bbox=best_bbox, matched_text=best_text, similarity=best_ratio)


@dataclass
class RoundLetterResult:
    found: bool
    flagged_ratios: List[float] = field(default_factory=list)
    checked_count: int = 0


def check_round_letter_ratios(
    composite_path: Path,
    bbox: Tuple[int, int, int, int],
    expected_text: str,
    *,
    plausible_ratio_band: Tuple[float, float] = _PLAUSIBLE_RATIO_BAND,
) -> RoundLetterResult:
    """Within bbox, measures the actual ink-pixel width/height of each
    glyph blob and flags ones that look non-uniformly squashed/stretched,
    but ONLY for blobs that line up with a known round letter (o/O/c/C/e/a)
    in expected_text - and only when the blob count roughly matches the
    non-space character count, so touching-letter kerning or wrapped lines
    don't get silently misread as something else.

    This is a heuristic safety net for OBVIOUS distortion, not a precise
    verifier: it will miss subtle cases and can misfire on unusual
    kerning/fonts. Meaningfully lower-confidence than check_uniform_scale.
    """
    non_space = expected_text.replace(" ", "")
    if not non_space:
        return RoundLetterResult(found=False)

    image = cv2.imread(str(composite_path))
    if image is None:
        return RoundLetterResult(found=False)

    x, y, w, h = bbox
    crop = image[max(0, y):y + h, max(0, x):x + w]
    if crop.size == 0:
        return RoundLetterResult(found=False)

    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    # Text is usually the minority-area class after Otsu; if the "foreground"
    # guess is actually the majority (background), invert.
    if np.count_nonzero(binary) > binary.size / 2:
        binary = cv2.bitwise_not(binary)

    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes = [cv2.boundingRect(c) for c in contours if cv2.contourArea(c) >= _CONTOUR_MIN_AREA]
    if not boxes:
        return RoundLetterResult(found=False)
    boxes.sort(key=lambda b: b[0])  # left-to-right, matching reading order

    if abs(len(boxes) - len(non_space)) > max(3, round(len(non_space) * 0.3)):
        # Blob count doesn't plausibly correspond to the expected characters
        # (touching letters, ligatures, wrapped lines) - report inconclusive
        # rather than mis-aligning positions and guessing.
        return RoundLetterResult(found=False, checked_count=0)

    flagged: List[float] = []
    checked = 0
    for char, box in zip(non_space, boxes):
        if char not in _ROUND_LETTERS:
            continue
        _, _, bw, bh = box
        if bh == 0:
            continue
        ratio = bw / bh
        checked += 1
        if not (plausible_ratio_band[0] <= ratio <= plausible_ratio_band[1]):
            flagged.append(ratio)

    return RoundLetterResult(found=True, flagged_ratios=flagged, checked_count=checked)


# --- Check 6b: CTA pill/button shape ------------------------------------------

@dataclass
class PillShapeResult:
    found: bool
    is_stadium_shape: bool = False
    fill_ratio: Optional[float] = None
    expected_fill_ratio: Optional[float] = None


def _hex_to_bgr(hex_color: str) -> Tuple[int, int, int]:
    hex_color = hex_color.lstrip("#")
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
    return b, g, r


def check_pill_shape(
    composite_path: Path, fill_hex: str, *, color_tolerance: int = 30, fill_ratio_tolerance: float = 0.03
) -> PillShapeResult:
    """The CTA pill has both a KNOWN exact fill color (fill_hex - a value
    the caller chose, not guessed) and a well-defined target shape family
    (a "fully-rounded pill": a rectangle with semicircular end-caps of
    radius = height/2, i.e. a stadium shape) - more checkable than the
    text-letterform checks, which have neither.

    Any ellipse inscribed in its own bounding box has a constant fill ratio
    of pi/4 regardless of aspect ratio; a plain rectangle has fill ratio 1.0.
    A true stadium's fill ratio varies smoothly between those two bounds
    with its own width/height ratio: expected = 1 - (h/w)*(1 - pi/4) for
    w >= h. Comparing the ACTUAL measured fill ratio against that formula
    catches both "stretched into an oval" (drifts toward pi/4 regardless of
    w/h) and "corners didn't round at all" (drifts toward 1.0).
    """
    image = cv2.imread(str(composite_path))
    if image is None:
        return PillShapeResult(found=False)

    target_bgr = np.array(_hex_to_bgr(fill_hex), dtype=np.int16)
    diff = np.abs(image.astype(np.int16) - target_bgr).sum(axis=2)
    mask = (diff <= color_tolerance * 3).astype(np.uint8) * 255
    # The CTA text sits ON TOP of the pill fill by design, carving
    # text-shaped holes out of the color mask - close over them (a small
    # morphological dilate+erode) so the measurement reflects the pill's
    # outer silhouette, not "fill colour minus whatever text overlaps it".
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (21, 21)))

    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    if num_labels <= 1:
        return PillShapeResult(found=False)

    # Largest non-background component by area.
    areas = stats[1:, cv2.CC_STAT_AREA]
    idx = int(np.argmax(areas)) + 1
    x, y, w, h, area = stats[idx]
    if w == 0 or h == 0:
        return PillShapeResult(found=False)

    long_side, short_side = max(w, h), min(w, h)
    fill_ratio = float(area) / float(w * h)
    expected = 1 - (short_side / long_side) * (1 - math.pi / 4)

    is_stadium = abs(fill_ratio - expected) <= fill_ratio_tolerance
    return PillShapeResult(found=True, is_stadium_shape=is_stadium, fill_ratio=fill_ratio, expected_fill_ratio=expected)
