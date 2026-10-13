"""Cache for SerpApi Google Lens responses.

Uses a SHA-256 fingerprint of input image content / parameters to guarantee
deterministic, privacy-conscious cache lookup without exposing raw image data
or calling SerpApi redundantly.
"""
import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

CACHE_DIR = Path.home() / ".veritrace" / "lens_cache"
DEFAULT_TTL_SECONDS = 7 * 24 * 3600  # 7 days


def _compute_cache_key(identifier: str, search_type: str, limit: int) -> str:
    """Compute stable hex digest for the search parameters and image identifier."""
    raw = f"{identifier}:{search_type}:{limit}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def get_cached_response(
    identifier: str,
    search_type: str = "all",
    limit: int = 20,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    cache_dir: Optional[Path] = None,
) -> Optional[dict]:
    """Retrieve cached SerpApi response payload if still valid within TTL."""
    c_dir = cache_dir or CACHE_DIR
    cache_key = _compute_cache_key(identifier, search_type, limit)
    cache_file = c_dir / f"{cache_key}.json"

    if not cache_file.is_file():
        return None

    try:
        data = json.loads(cache_file.read_text(encoding="utf-8"))
        cached_at = data.get("_cached_at")
        if cached_at:
            dt = datetime.fromisoformat(cached_at)
            age = (datetime.now(timezone.utc) - dt).total_seconds()
            if age > ttl_seconds:
                logger.info("Cache entry %s expired (age %.1fs > ttl %ds)", cache_key, age, ttl_seconds)
                return None
        return data.get("payload")
    except Exception as exc:
        logger.warning("Failed to read cache file %s: %exc", cache_file, exc)
        return None


def store_cached_response(
    identifier: str,
    search_type: str,
    limit: int,
    payload: dict,
    cache_dir: Optional[Path] = None,
) -> Path:
    """Store SerpApi response payload in cache without storing any API keys."""
    c_dir = cache_dir or CACHE_DIR
    c_dir.mkdir(parents=True, exist_ok=True)
    cache_key = _compute_cache_key(identifier, search_type, limit)
    cache_file = c_dir / f"{cache_key}.json"

    record = {
        "cache_key": cache_key,
        "identifier_hash": hashlib.sha256(identifier.encode("utf-8")).hexdigest(),
        "search_type": search_type,
        "limit": limit,
        "_cached_at": datetime.now(timezone.utc).isoformat(),
        "payload": payload,
    }

    cache_file.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return cache_file
