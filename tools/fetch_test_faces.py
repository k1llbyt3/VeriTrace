"""Fetch a few freely-licensed photos from Wikipedia as neutral calibration data.

Purpose: measure what cosine similarity this ArcFace model actually gives for
"same person" vs "different person" pairs, so FACE_SIMILARITY_THRESHOLD is a
measured number rather than a guess. Not part of the pipeline.

Usage:  python tools/fetch_test_faces.py Sunita_Williams Kalpana_Chawla
"""
from pathlib import Path
import sys

import requests

HEADERS = {"User-Agent": "hh-goa-2026-task3/0.1 (threshold calibration test data)"}
OUT_DIR = Path(__file__).resolve().parent.parent / "samples" / "calib"
API = "https://en.wikipedia.org/api/rest_v1/page/media-list/"


def image_urls(title: str, limit: int = 4) -> list[str]:
    response = requests.get(API + title, headers=HEADERS, timeout=30)
    response.raise_for_status()
    urls = []
    for item in response.json().get("items", []):
        if item.get("type") != "image":
            continue
        for source in item.get("srcset") or []:
            src = source.get("src", "")
            if src.split("?")[0].lower().endswith((".jpg", ".jpeg", ".png")):
                urls.append("https:" + src if src.startswith("//") else src)
                break
        if len(urls) >= limit:
            break
    return urls


def main(titles: list[str]) -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for title in titles:
        slug = title.lower().replace("_", "-")
        for index, url in enumerate(image_urls(title), start=1):
            dest = OUT_DIR / f"{slug}-{index}.jpg"
            try:
                response = requests.get(url, headers=HEADERS, timeout=60)
                response.raise_for_status()
                dest.write_bytes(response.content)
                print(f"saved {dest.name}  ({len(response.content) // 1024} KB)")
            except requests.RequestException as exc:
                print(f"skipped {url}: {exc}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(1)
    raise SystemExit(main(sys.argv[1:]))
