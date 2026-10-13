"""Download and preserve exact image response bytes for an evidence case safely."""
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

import config
from search.lens import LensCandidate
from search.security import SecurityError, validate_public_url


class DownloadError(RuntimeError):
    """The requested image could not be safely downloaded."""


_CONTENT_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


def _extension(url: str, content_type: str, fallback: str = ".bin") -> str:
    extension = _CONTENT_EXTENSIONS.get(content_type.split(";", 1)[0].lower())
    if extension:
        return extension
    suffix = Path(urlparse(url).path).suffix.lower()
    return suffix if suffix in {".jpg", ".jpeg", ".png", ".webp"} else fallback


def download_image(url: str, destination: Path, max_bytes: int = None) -> int:
    """Download an accessible image and write its response bytes unchanged.

    Validates URL safety, prevents SSRF, and enforces maximum size constraints.
    """
    if max_bytes is None:
        max_bytes = getattr(config, "MAX_IMAGE_DOWNLOAD_BYTES", 15 * 1024 * 1024)

    # Validate URL against SSRF
    try:
        url = validate_public_url(url)
    except SecurityError as exc:
        raise DownloadError(f"Security validation rejected image URL: {exc}") from exc

    try:
        response = requests.get(
            url,
            timeout=30,
            headers={"User-Agent": "VeriTrace evidence downloader/1.0"},
            stream=True,
            allow_redirects=True,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise DownloadError(f"download failed: {exc}") from exc

    content_type = response.headers.get("content-type", "")
    # Check if declared content type is image (or octet-stream fallback)
    if not (content_type.lower().startswith("image/") or "octet-stream" in content_type.lower()):
        raise DownloadError(f"response is not an image ({content_type or 'missing content type'})")

    content_length = response.headers.get("content-length")
    if content_length and int(content_length) > max_bytes:
        raise DownloadError(f"image size ({content_length} bytes) exceeds limit ({max_bytes} bytes)")

    # Read chunks safely enforcing max_bytes
    chunks = []
    total_bytes = 0
    for chunk in response.iter_content(chunk_size=65536):
        if not chunk:
            continue
        total_bytes += len(chunk)
        if total_bytes > max_bytes:
            raise DownloadError(f"download stream exceeded max size limit of {max_bytes} bytes")
        chunks.append(chunk)

    data = b"".join(chunks)
    if not data:
        raise DownloadError("image response was empty")

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)
    return len(data)


def preserve_case(input_url: str, candidates: list[LensCandidate], case_dir: Path) -> dict:
    """Preserve the input and first accessible candidate with a JSON manifest."""
    case_dir.mkdir(parents=True, exist_ok=True)
    input_extension = _extension(input_url, "")
    input_filename = f"input{input_extension}"
    input_path = case_dir / input_filename
    input_size = download_image(input_url, input_path)

    failures: list[str] = []
    for index, candidate in enumerate(candidates, start=1):
        if not candidate.image_url:
            failures.append(f"{candidate.candidate_id}: no image URL")
            continue
        candidate_extension = _extension(candidate.image_url, "", fallback=".jpg")
        candidate_filename = f"candidate-{index:03d}{candidate_extension}"
        candidate_path = case_dir / candidate_filename
        try:
            candidate_size = download_image(candidate.image_url, candidate_path)
        except DownloadError as exc:
            failures.append(f"{candidate.candidate_id}: {exc}")
            continue
        metadata = {
            "retrieval_timestamp": datetime.now(timezone.utc).isoformat(),
            "input": {"source_url": input_url, "local_artifact_filename": input_filename, "size_bytes": input_size},
            "candidate": {**candidate.as_dict(), "local_artifact_filename": candidate_filename, "size_bytes": candidate_size},
        }
        (case_dir / "metadata.json").write_text(
            json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
        )
        return metadata
    raise DownloadError("no accessible candidate image: " + "; ".join(failures))
