"""Supabase Storage-backed storage for uploaded/generated images. The DB
stores the full public URL (see app.models.AngleImage columns file_path,
reference_image_path, logo_path, and the JSON-encoded company_image_paths).

Generation (app.agents.meta_ads.image_generation) needs real file bytes to send
to OpenAI, so `download_to_temp_file` fetches a stored URL to a local temp
file on demand — see app.services.angle_image_service.
"""

import base64
import binascii
import tempfile
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import requests

from app.config import SUPABASE_SERVICE_ROLE_KEY, SUPABASE_STORAGE_BUCKET, SUPABASE_URL
from app.errors import ServiceNotConfiguredError, UpstreamServiceError

_STORAGE_API = f"{SUPABASE_URL}/storage/v1" if SUPABASE_URL else None
_SERVICE = "Supabase Storage"


def _require_config() -> None:
    """Without these the upload URL would be "None/storage/v1/…" and the failure
    would surface as a confusing connection error rather than a config problem."""
    if not _STORAGE_API or not SUPABASE_SERVICE_ROLE_KEY:
        raise ServiceNotConfiguredError(
            "Image storage",
            internal="SUPABASE_URL and/or SUPABASE_SERVICE_ROLE_KEY is unset",
        )


def _auth_headers(content_type: str = "application/octet-stream") -> dict:
    return {
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Content-Type": content_type,
    }


def _new_object_path(original_name: str, subdir: str) -> str:
    suffix = Path(original_name).suffix or ".png"
    return f"{subdir}/{uuid.uuid4().hex}{suffix}"


def _public_url(object_path: str) -> str:
    return f"{_STORAGE_API}/object/public/{SUPABASE_STORAGE_BUCKET}/{object_path}"


def save_upload_bytes(content: bytes, original_name: str, subdir: str) -> str:
    """Uploads raw bytes to Supabase Storage under <subdir>/ and returns the
    public URL to store in the DB.
    """
    _require_config()
    object_path = _new_object_path(original_name, subdir)
    try:
        response = requests.post(
            f"{_STORAGE_API}/object/{SUPABASE_STORAGE_BUCKET}/{object_path}",
            headers=_auth_headers(),
            data=content,
            timeout=30,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        # The response body can echo back the service_role key's claims, so it
        # goes to the log, never to the caller.
        raise UpstreamServiceError(
            _SERVICE,
            "Couldn't save the image. Please try again in a moment.",
            internal=f"upload {object_path} failed: {exc}",
        ) from exc
    return _public_url(object_path)


def save_base64_image(b64_data: str, subdir: str, ext: str = ".png") -> str:
    """Decodes a base64 image (e.g. OpenAI images API b64_json) and uploads
    it to Supabase Storage, returning the public URL to store in the DB.
    """
    try:
        content = base64.b64decode(b64_data)
    except (binascii.Error, ValueError) as exc:
        raise UpstreamServiceError(
            "Image generation",
            "The generated image came back unreadable. Please try again.",
            internal=f"base64 decode failed: {exc}",
        ) from exc
    return save_upload_bytes(content, f"generated{ext}", subdir)


@contextmanager
def download_to_temp_file(url: str) -> Iterator[Path]:
    """Downloads a stored URL to a temp file for the duration of the `with`
    block, then deletes it. Used by the image generation agents, which need
    a real local path to open() and send to OpenAI's API.
    """
    suffix = Path(url.split("?")[0]).suffix or ".png"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise UpstreamServiceError(
                _SERVICE,
                "Couldn't load a stored image. Please try again in a moment.",
                internal=f"download {url} failed: {exc}",
            ) from exc
        tmp_path.write_bytes(response.content)
        yield tmp_path
    finally:
        tmp_path.unlink(missing_ok=True)


def delete_file(url: str) -> None:
    """Deletes an image from Supabase Storage given its public URL."""
    marker = f"/object/public/{SUPABASE_STORAGE_BUCKET}/"
    if marker not in url:
        return
    object_path = url.split(marker, 1)[1]
    try:
        response = requests.delete(
            f"{_STORAGE_API}/object/{SUPABASE_STORAGE_BUCKET}/{object_path}",
            headers=_auth_headers(),
            timeout=30,
        )
        response.raise_for_status()
    except requests.RequestException:
        pass
