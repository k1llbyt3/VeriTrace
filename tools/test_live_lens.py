"""Explicit live integration test script for SerpApi Google Lens.

IMPORTANT:
  1. Only runs when explicitly triggered by the user via command line:
       python tools/test_live_lens.py
  2. Requires a real SERPAPI_KEY configured in .env.
  3. Uses exactly ONE request with a low candidate limit (limit=3) to conserve API quota.
  4. Never automatically retries on failure.
"""
import sys
from pathlib import Path
import config
from search.lens import search_google_lens, LensCandidate
from face.engine import get_engine
from pipeline import select_candidate

# Add project root and python/ directory to path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))



TEST_IMAGE_URL = "https://upload.wikimedia.org/wikipedia/commons/b/b3/Sunita_Williams_2018.jpg"
LOCAL_TEST_IMAGE = ROOT / "samples" / "calib" / "sunita-williams-1.jpg"


def main():
    print("=" * 60)
    print("VERITRACE — LIVE GOOGLE LENS INTEGRATION TEST")
    print("=" * 60)

    # 1. Validate key presence without printing it
    if not config.SERPAPI_KEY:
        print("\n[ERROR] SERPAPI_KEY is not configured in .env.")
        print("Please configure SERPAPI_KEY=<your_key> in .env and re-run.")
        return 1

    key_len = len(config.SERPAPI_KEY)
    masked_key = config.SERPAPI_KEY[:4] + ("*" * (key_len - 8)) + config.SERPAPI_KEY[-4:] if key_len >= 8 else "***"
    print(f"\n[OK] SERPAPI_KEY detected: {masked_key} (length: {key_len})")
    print(f"[OK] Reference test URL: {TEST_IMAGE_URL}")

    # 2. Run ONE live search with a small limit
    print("\nExecuting 1 live SerpApi request (type: visual_matches, limit: 3)...")
    try:
        candidates = search_google_lens(
            TEST_IMAGE_URL,
            search_type="visual_matches",
            limit=3,
            force_refresh=True,
        )
    except Exception as exc:
        print(f"\n[FAIL] Live search failed: {exc}")
        return 1

    print(f"[OK] Live request successful! Retrieved {len(candidates)} candidates.")
    for idx, c in enumerate(candidates, 1):
        print(f"  {idx}. [{c.search_type} #{c.search_rank}] {c.title or '(untitled)'}")
        print(f"     Source: {c.domain} | URL: {c.source_url}")
        print(f"     Image:  {c.image_url}")

    # 3. Test face evaluation on candidates if local image is available
    if LOCAL_TEST_IMAGE.is_file() and candidates:
        print(f"\nTesting face comparison with local reference: {LOCAL_TEST_IMAGE.name}")
        case_id = "live-test-001"
        try:
            result = select_candidate(
                input_image=str(LOCAL_TEST_IMAGE),
                case_id=case_id,
                candidates=candidates,  # Reuses fetched candidates, NO extra SerpApi request!
                threshold=config.FACE_SIMILARITY_THRESHOLD,
            )
            print(f"[OK] Candidate evaluation complete: {result.evaluated} evaluated, {result.qualifying} qualifying.")
            if result.selected:
                print(f"[OK] Selected candidate: {result.selected.candidate.title} (similarity: {result.selected.best_face_similarity:.4f})")
            else:
                print("[INFO] No candidates passed similarity threshold.")
        except Exception as exc:
            print(f"[FAIL] Candidate face evaluation failed: {exc}")
            return 1

    print("\n" + "=" * 60)
    print("LIVE INTEGRATION TEST COMPLETE — TOTAL API REQUESTS MADE: 1")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
