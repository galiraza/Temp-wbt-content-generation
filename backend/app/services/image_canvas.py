"""Fits a generated post image to an exact output canvas size, without the
extra Gemini outpainting round-trip the n8n workflow used.

The key fact this relies on (verified empirically against the real API, not
assumed): gpt-image-2's images.edit() honors an arbitrary "WIDTHxHEIGHT" size
string, as long as both dimensions are divisible by 16. 1080x1350 (the
target, 4:5 portrait) isn't itself divisible by 16, but 1088x1360 is exactly
proportional to it (both are 1080:1350 scaled by 68/85 -> 16), so requesting
"1088x1360" from the generation call and then downscaling the result by the
~0.7% needed to reach 1080x1350 is a PURE UNIFORM scale - it cannot introduce
non-uniform stretch, unlike an outpaint/extend operation.

fit_to_canvas() never assumes the API actually honored the requested size -
it reads the real dimensions of what came back and dispatches accordingly,
cheapest/safest option first. See PLAN.md (image pipeline plan) for why
cv2.inpaint/seamlessClone and a local generative outpainting model were
both considered and rejected for the fallback path.
"""

import io
from typing import Tuple

import cv2
import numpy as np
from PIL import Image

TARGET_SIZE: Tuple[int, int] = (1080, 1350)  # (width, height)
EDIT_REQUEST_SIZE = "1088x1360"  # pass to images.edit(size=...): exact 4:5, both /16

# How close the actual returned aspect ratio must be to the target's before
# a mirror-and-feather extension (rather than a plain crop) is used to close
# the gap. 3% is generous enough to cover normal API rounding/variance while
# staying well short of "the model ignored the requested size entirely".
_NEAR_RATIO_TOLERANCE = 0.03
_FEATHER_PX = 30


def fit_to_canvas(image_bytes: bytes, target_size: Tuple[int, int] = TARGET_SIZE) -> bytes:
    """PNG bytes in -> PNG bytes out at exactly target_size, whatever the
    input's actual dimensions turn out to be.
    """
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    target_w, target_h = target_size
    target_ratio = target_w / target_h
    actual_ratio = image.width / image.height

    if abs(actual_ratio - target_ratio) / target_ratio < 0.005:
        result = _uniform_resize(image, target_size)
    elif abs(actual_ratio - target_ratio) / target_ratio < _NEAR_RATIO_TOLERANCE:
        result = _extend_with_mirrored_background(image, target_size)
    else:
        result = _center_crop(image, target_size)

    out = io.BytesIO()
    result.save(out, format="PNG")
    return out.getvalue()


def _uniform_resize(image: Image.Image, target_size: Tuple[int, int]) -> Image.Image:
    """The expected case: input is already (near-)exactly the target ratio,
    so a single resize by the same factor on both axes gets to target_size
    with no distortion whatsoever."""
    return image.resize(target_size, Image.LANCZOS)


def _extend_with_mirrored_background(image: Image.Image, target_size: Tuple[int, int]) -> Image.Image:
    """Input is a bit off-ratio (small API variance) - extend the shorter
    axis by mirroring the edge strip, then feather the seam so it isn't a
    visible hard line. This only produces a convincing result because this
    design's background is a soft, mostly-flat gradient (see
    final_image_prompt.py) with no photographic texture near the canvas
    edge - mirroring a smooth gradient still looks like a smooth gradient.
    """
    target_w, target_h = target_size
    target_ratio = target_w / target_h

    # First bring the image to the target's WIDTH (or height) via a uniform
    # scale, so only one axis needs extending, never both.
    if image.width / image.height > target_ratio:
        # Too wide relative to target -> scale to match target height, extend width.
        scale = target_h / image.height
        scaled = image.resize((round(image.width * scale), target_h), Image.LANCZOS)
        needed = target_w - scaled.width
        axis = "width"
    else:
        # Too tall relative to target -> scale to match target width, extend height.
        scale = target_w / image.width
        scaled = image.resize((target_w, round(image.height * scale)), Image.LANCZOS)
        needed = target_h - scaled.height
        axis = "height"

    if needed <= 0:
        # Scaling to match the other axis already overshot target_size (can
        # happen right at the tolerance boundary) - a crop closes it cleanly.
        return _center_crop(scaled, target_size)

    top = needed // 2
    bottom = needed - top
    left = needed // 2 if axis == "width" else 0
    right = needed - left if axis == "width" else 0

    arr = np.array(scaled)
    if axis == "width":
        extended = cv2.copyMakeBorder(arr, 0, 0, left, right, cv2.BORDER_REFLECT_101)
    else:
        extended = cv2.copyMakeBorder(arr, top, bottom, 0, 0, cv2.BORDER_REFLECT_101)

    extended = _feather_seam(extended, axis, left if axis == "width" else top,
                              right if axis == "width" else bottom, scaled)
    return Image.fromarray(extended).crop((0, 0, target_w, target_h))


def _feather_seam(extended: np.ndarray, axis: str, lead: int, trail: int, original: Image.Image) -> np.ndarray:
    """Blurs a narrow band straddling each mirror seam so the join isn't a
    visible hard edge, without touching the interior of the original image.
    """
    if lead == 0 and trail == 0:
        return extended
    blurred = cv2.GaussianBlur(extended, (0, 0), sigmaX=_FEATHER_PX / 2)
    mask = np.zeros(extended.shape[:2], dtype=np.uint8)
    band = min(_FEATHER_PX, lead, trail) if (lead and trail) else _FEATHER_PX
    if axis == "width":
        if lead:
            mask[:, max(0, lead - band):lead + band] = 255
        if trail:
            w = extended.shape[1]
            mask[:, w - trail - band:min(w, w - trail + band)] = 255
    else:
        if lead:
            mask[max(0, lead - band):lead + band, :] = 255
        if trail:
            h = extended.shape[0]
            mask[h - trail - band:min(h, h - trail + band), :] = 255
    mask3 = cv2.merge([mask, mask, mask]).astype(bool)
    return np.where(mask3, blurred, extended)


def _center_crop(image: Image.Image, target_size: Tuple[int, int]) -> Image.Image:
    """Last resort: scale to fully cover target_size, then crop the excess
    from the centre. Never distorts, never invents content."""
    target_w, target_h = target_size
    target_ratio = target_w / target_h
    if image.width / image.height > target_ratio:
        scale = target_h / image.height
    else:
        scale = target_w / image.width
    scaled = image.resize((round(image.width * scale), round(image.height * scale)), Image.LANCZOS)
    left = (scaled.width - target_w) // 2
    top = (scaled.height - target_h) // 2
    return scaled.crop((left, top, left + target_w, top + target_h))
