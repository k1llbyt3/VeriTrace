"""SerpApi Google Lens client, normalized candidate parsing, caching, and SSRF protection."""
import logging
from dataclasses import asdict, dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import requests

import config
from search.cache import get_cached_response, store_cached_response
from search.security import SecurityError, validate_public_url

logger = logging.getLogger(__name__)


class SearchError(RuntimeError):
    """A configuration, transport, quota, or SerpApi response error."""


class QuotaExhaustedError(SearchError):
    """Raised when SerpApi reports monthly or plan search quota has been exhausted."""


class AuthenticationError(SearchError):
    """Raised when SerpApi API key is invalid or unauthorized."""


class _OpenGraphImageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.image_url = ""

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "meta" or self.image_url:
            return
        attributes = {key.lower(): value for key, value in attrs}
        if attributes.get("property", "").lower() == "og:image":
            self.image_url = (attributes.get("content") or "").strip()


def resolve_public_image_url(source_url: str) -> str:
    """Resolve a direct image URL or a public page's Open Graph image safely."""
    # First apply SSRF validation
    try:
        source_url = validate_public_url(source_url)
    except SecurityError as exc:
        raise SearchError(f"Security validation failed for source URL: {exc}") from exc

    parsed = urlparse(source_url)
    if Path(parsed.path).suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
        return source_url

    try:
        response = requests.get(
            source_url,
            timeout=30,
            headers={"User-Agent": "VeriTrace evidence resolver/1.0"},
            allow_redirects=True,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise SearchError(f"Could not fetch public image page: {exc}") from exc

    parser = _OpenGraphImageParser()
    parser.feed(response.text)
    image_url = parser.image_url
    if not image_url:
        raise SearchError("Public page did not provide a usable og:image metadata tag.")

    # Validate the discovered image URL
    try:
        image_url = validate_public_url(image_url)
    except SecurityError as exc:
        raise SearchError(f"Discovered image URL violates security constraints: {exc}") from exc

    return image_url


@dataclass(frozen=True)
class LensCandidate:
    candidate_id: str
    title: str
    source_url: str
    image_url: str
    domain: str
    search_type: str
    search_rank: int

    def as_dict(self) -> dict[str, str | int]:
        return asdict(self)


def _domain(source_url: str, source: str) -> str:
    try:
        hostname = urlparse(source_url).hostname
        return hostname.removeprefix("www.") if hostname else source
    except Exception:
        return source


def parse_candidates(payload: dict, limit: int = 20) -> list[LensCandidate]:
    """Normalize exact and visual Lens arrays into the project candidate shape."""
    candidates: list[LensCandidate] = []
    seen: set[tuple[str, str]] = set()

    # SerpApi returns exact_matches and visual_matches
    sections = (
        ("exact_matches", payload.get("exact_matches", [])),
        ("visual_matches", payload.get("visual_matches", [])),
    )

    for search_type, results in sections:
        if not isinstance(results, list):
            continue
        for fallback_rank, result in enumerate(results, start=1):
            if not isinstance(result, dict):
                continue

            source_url = str(result.get("link") or result.get("url") or "").strip()
            image_url = str(result.get("image") or result.get("thumbnail") or "").strip()

            # Skip candidate if both source and image are empty
            if not source_url and not image_url:
                continue

            # Deduplicate by (source_url, image_url)
            identity = (source_url, image_url)
            if identity in seen:
                continue
            seen.add(identity)

            rank = result.get("position", fallback_rank)
            try:
                rank = int(rank)
            except (TypeError, ValueError):
                rank = fallback_rank

            source = str(result.get("source") or "").strip()
            candidates.append(
                LensCandidate(
                    candidate_id=f"{search_type}-{rank}",
                    title=str(result.get("title") or "").strip(),
                    source_url=source_url,
                    image_url=image_url,
                    domain=_domain(source_url, source),
                    search_type=search_type,
                    search_rank=rank,
                )
            )

            if len(candidates) >= limit:
                return candidates

    return candidates


SUPPORTED_UPLOAD_FORMATS = {
    "JPEG": ("image/jpeg", ".jpg"),
    "JPG": ("image/jpeg", ".jpg"),
    "PNG": ("image/png", ".png"),
    "WEBP": ("image/webp", ".webp"),
}
MAX_SERPAPI_IMAGE_SIZE_BYTES = 500 * 1024  # 500 KB limit documented by SerpApi


def prepare_image_for_upload(
    image_input: str | Path | bytes,
    max_bytes: int = MAX_SERPAPI_IMAGE_SIZE_BYTES,
    filename: Optional[str] = None,
) -> tuple[bytes, str, str]:
    """Validate format and prepare image bytes for SerpApi Image API (<= 500 KB).

    Strictly preserves aspect ratio if resizing is required.
    Supported formats: JPG/JPEG, PNG, WebP.
    Returns: (data_bytes, mime_type, filename)
    """
    from io import BytesIO
    from PIL import Image, ImageOps

    if isinstance(image_input, (str, Path)):
        path = Path(image_input)
        if not path.is_file():
            raise SearchError(f"Image file does not exist: {path}")
        raw_bytes = path.read_bytes()
        default_filename = path.name
    else:
        raw_bytes = bytes(image_input)
        default_filename = filename or "image.jpg"

    if not raw_bytes:
        raise SearchError("Cannot prepare empty image for upload")

    try:
        with Image.open(BytesIO(raw_bytes)) as img:
            fmt = (img.format or "").upper()
            if fmt not in SUPPORTED_UPLOAD_FORMATS:
                raise SearchError(
                    f"Unsupported image format {fmt!r}. "
                    "SerpApi Image API supports JPG/JPEG, PNG, and WebP."
                )

            mime_type, default_ext = SUPPORTED_UPLOAD_FORMATS[fmt]
            save_format = "JPEG" if fmt in ("JPEG", "JPG") else fmt
            out_filename = filename or (Path(default_filename).stem + default_ext)

            # If already within limit, return original bytes untouched
            if len(raw_bytes) <= max_bytes:
                return raw_bytes, mime_type, out_filename

            orig_w, orig_h = img.size
            if orig_w <= 0 or orig_h <= 0:
                raise SearchError(f"Invalid image dimensions: {orig_w}x{orig_h}")

            # Correct orientation if EXIF present
            img = ImageOps.exif_transpose(img) or img
            if save_format == "JPEG" and img.mode in ("RGBA", "P"):
                img = img.convert("RGB")

            # Iteratively compress / resize while preserving aspect ratio
            curr_img = img.copy()
            current_w, current_h = orig_w, orig_h
            quality = 90

            for _ in range(15):
                buf = BytesIO()
                save_kwargs = {}
                if save_format in ("JPEG", "WEBP"):
                    save_kwargs["quality"] = quality
                    if save_format == "JPEG":
                        save_kwargs["optimize"] = True
                curr_img.save(buf, format=save_format, **save_kwargs)
                compressed = buf.getvalue()

                if len(compressed) <= max_bytes:
                    return compressed, mime_type, out_filename

                if quality > 65 and save_format in ("JPEG", "WEBP"):
                    quality -= 10
                else:
                    scale_factor = min(0.85, (max_bytes / len(compressed)) ** 0.5 * 0.95)
                    new_w = max(16, int(round(current_w * scale_factor)))
                    # Aspect ratio: strictly new_h / new_w == orig_h / orig_w
                    new_h = max(16, int(round(new_w * (orig_h / orig_w))))
                    curr_img = curr_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
                    current_w, current_h = new_w, new_h
                    quality = 85

            buf = BytesIO()
            curr_img.save(buf, format=save_format, quality=50 if save_format in ("JPEG", "WEBP") else None)
            final_bytes = buf.getvalue()
            if len(final_bytes) > max_bytes:
                target_w = 400
                target_h = max(16, int(round(target_w * (orig_h / orig_w))))
                curr_img = curr_img.resize((target_w, target_h), Image.Resampling.LANCZOS)
                buf = BytesIO()
                curr_img.save(buf, format=save_format, quality=50 if save_format in ("JPEG", "WEBP") else None)
                final_bytes = buf.getvalue()

            return final_bytes, mime_type, out_filename
    except Exception as exc:
        if isinstance(exc, SearchError):
            raise
        raise SearchError(f"Failed to prepare image for upload: {exc}") from exc


def upload_image_to_serpapi(
    image_input: str | Path | bytes,
    api_key: Optional[str] = None,
    filename: Optional[str] = None,
) -> str:
    """Upload a local image to SerpApi's Image API and return its temporary image_id.

    Official docs: https://serpapi.com/image-api
    Endpoint: POST https://serpapi.com/image (multipart/form-data)
    The returned image_id expires after 10 minutes.
    """
    api_key = api_key or config.SERPAPI_KEY
    if not api_key:
        raise AuthenticationError(
            "SERPAPI_KEY is not configured in .env. "
            "Please obtain an API key from https://serpapi.com/manage-api-key and set SERPAPI_KEY=... in .env"
        )

    data_bytes, mime_type, file_name = prepare_image_for_upload(image_input, filename=filename)

    try:
        files = {
            "image": (file_name, data_bytes, mime_type)
        }
        data = {
            "api_key": api_key
        }
        response = requests.post(
            "https://serpapi.com/image",
            files=files,
            data=data,
            timeout=60,
        )
    except requests.RequestException as exc:
        raise SearchError(f"SerpApi Image API upload request failed: {exc}") from exc

    if response.status_code in (401, 403):
        raise AuthenticationError("SerpApi authentication failed: Invalid or unauthorized API key.")
    if response.status_code == 429:
        raise QuotaExhaustedError("SerpApi rate limit or search quota exhausted.")

    try:
        payload = response.json()
    except ValueError as exc:
        raise SearchError(f"SerpApi Image API returned non-JSON response (status {response.status_code})") from exc

    error_msg = payload.get("error")
    if error_msg:
        error_str = str(error_msg).lower()
        if "invalid api key" in error_str or "private api key" in error_str:
            raise AuthenticationError("SerpApi authentication failed: Invalid API key.")
        if "quota" in error_str or ("searches" in error_str and "run out" in error_str):
            raise QuotaExhaustedError(f"SerpApi search quota exhausted: {error_msg}")
        raise SearchError(f"SerpApi Image API error: {error_msg}")

    image_id = payload.get("image_id")
    if not image_id:
        raise SearchError(f"SerpApi Image API did not return an image_id: {payload}")

    return str(image_id)


def search_google_lens(
    image_url: Optional[str] = None,
    image_id: Optional[str] = None,
    image_path: Optional[Path | str] = None,
    search_type: str = "all",
    limit: int = 20,
    force_refresh: bool = False,
    dry_run: bool = False,
) -> list[LensCandidate]:
    """Run a Google Lens search through SerpApi using a URL, image_id, or local image_path.

    Official docs:
      https://serpapi.com/google-lens-api
      https://serpapi.com/image-api
    """
    if search_type not in {"all", "exact_matches", "visual_matches"}:
        raise SearchError(f"Invalid search type {search_type!r}. Must be all, exact_matches, or visual_matches")
    if limit < 1:
        raise SearchError("Limit must be at least 1")

    if not image_url and not image_id and not image_path:
        raise SearchError("One of image_url, image_id, or image_path must be provided for Lens search.")

    resolved_target = ""
    target_image_id = image_id or ""

    # Validate / prepare inputs
    if image_path:
        prepare_image_for_upload(image_path)
        from evidence.hashing import sha256_file
        resolved_target = f"file:{sha256_file(image_path)}"
    elif image_url:
        resolved_target = resolve_public_image_url(image_url)
    elif image_id:
        resolved_target = f"image_id:{image_id}"

    # Check cache if enabled
    if config.LENS_CACHE_ENABLED and not force_refresh:
        cached_payload = get_cached_response(
            resolved_target,
            search_type=search_type,
            limit=limit,
            ttl_seconds=config.LENS_CACHE_TTL,
        )
        if cached_payload is not None:
            logger.info("Serving Google Lens results from cache for %s", resolved_target)
            return parse_candidates(cached_payload, limit=limit)

    # Dry-run validation mode: validate inputs and stop before hitting API
    if dry_run:
        logger.info("Dry-run mode: parameters validated successfully for %s", resolved_target)
        return []

    # Check API key presence
    api_key = config.SERPAPI_KEY
    if not api_key:
        raise SearchError(
            "SERPAPI_KEY is not configured in .env. "
            "Please obtain an API key from https://serpapi.com/manage-api-key and set SERPAPI_KEY=... in .env"
        )

    # If image_path was given and target_image_id not set, upload to SerpApi Image API
    if image_path and not target_image_id:
        target_image_id = upload_image_to_serpapi(image_path, api_key=api_key)

    # Execute search request
    try:
        params = {
            "engine": "google_lens",
            "api_key": api_key,
        }
        if target_image_id:
            params["image_id"] = target_image_id
        else:
            params["url"] = resolved_target

        if search_type != "all":
            params["type"] = search_type

        response = requests.get(
            "https://serpapi.com/search.json",
            params=params,
            timeout=60,
        )
    except requests.RequestException as exc:
        raise SearchError(f"SerpApi network request failed: {exc}") from exc

    if response.status_code in (401, 403):
        raise AuthenticationError("SerpApi authentication failed: Invalid or unauthorized API key.")
    if response.status_code == 429:
        raise QuotaExhaustedError("SerpApi rate limit or search quota exhausted.")

    try:
        payload = response.json()
    except ValueError as exc:
        raise SearchError(f"SerpApi returned invalid non-JSON response (status {response.status_code})") from exc

    # Inspect SerpApi error fields
    error_msg = payload.get("error")
    if error_msg:
        error_str = str(error_msg).lower()
        if "invalid api key" in error_str or "private api key" in error_str:
            raise AuthenticationError("SerpApi authentication failed: Invalid API key.")
        if "quota" in error_str or ("searches" in error_str and "run out" in error_str):
            raise QuotaExhaustedError(f"SerpApi search quota exhausted: {error_msg}")
        if "google lens hasn't returned any results" in error_str or "no results" in error_str:
            return []
        raise SearchError(f"SerpApi query error: {error_msg}")

    # Store in cache
    if config.LENS_CACHE_ENABLED:
        store_cached_response(resolved_target, search_type, limit, payload)

    return parse_candidates(payload, limit=limit)
