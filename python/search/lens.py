"""SerpApi Google Lens client and normalized candidate parsing."""
from dataclasses import asdict, dataclass
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

import requests

import config


class SearchError(RuntimeError):
    """A configuration, transport, or SerpApi response error."""


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
    """Resolve a direct image URL or a public page's Open Graph image."""
    parsed = urlparse(source_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise SearchError("Image source must be an accessible http(s) URL.")
    if Path(parsed.path).suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
        return source_url

    try:
        response = requests.get(
            source_url,
            timeout=30,
            headers={"User-Agent": "Goaa evidence resolver/1.0"},
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise SearchError(f"Could not fetch public image page: {exc}") from exc

    parser = _OpenGraphImageParser()
    parser.feed(response.text)
    image_url = parser.image_url
    image_parsed = urlparse(image_url)
    if image_parsed.scheme not in {"http", "https"} or not image_parsed.netloc:
        raise SearchError("Public page did not provide a usable externally accessible image URL.")
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
    hostname = urlparse(source_url).hostname
    return hostname.removeprefix("www.") if hostname else source


def parse_candidates(payload: dict, limit: int = 20) -> list[LensCandidate]:
    """Normalize exact and visual Lens arrays into the project candidate shape."""
    candidates: list[LensCandidate] = []
    seen: set[tuple[str, str]] = set()
    sections = (("exact_matches", payload.get("exact_matches", [])), ("visual_matches", payload.get("visual_matches", [])))
    for search_type, results in sections:
        if not isinstance(results, list):
            continue
        for fallback_rank, result in enumerate(results, start=1):
            if not isinstance(result, dict):
                continue
            source_url = str(result.get("link") or result.get("url") or "").strip()
            image_url = str(result.get("image") or result.get("thumbnail") or "").strip()
            if not source_url and not image_url:
                continue
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


def search_google_lens(image_url: str, search_type: str = "all", limit: int = 20) -> list[LensCandidate]:
    """Run a genuine Google Lens search through SerpApi using an image URL."""
    if not config.SERPAPI_KEY:
        raise SearchError("SERPAPI_KEY is not configured. Add SERPAPI_KEY=... to the root .env file.")
    image_url = resolve_public_image_url(image_url)
    parsed = urlparse(image_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise SearchError("Google Lens requires an accessible http(s) image URL.")
    if search_type not in {"all", "exact_matches", "visual_matches"}:
        raise SearchError("search type must be all, exact_matches, or visual_matches")
    if limit < 1:
        raise SearchError("limit must be at least 1")

    try:
        response = requests.get(
            "https://serpapi.com/search.json",
            params={"engine": "google_lens", "url": image_url, "type": search_type, "api_key": config.SERPAPI_KEY},
            timeout=60,
        )
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        raise SearchError(f"SerpApi request failed: {exc}") from exc
    except ValueError as exc:
        raise SearchError("SerpApi returned invalid JSON") from exc

    if payload.get("error"):
        error = str(payload["error"])
        if "Google Lens hasn't returned any results" in error:
            return []
        raise SearchError(f"SerpApi error: {error}")
    return parse_candidates(payload, limit=limit)
