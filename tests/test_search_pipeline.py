"""Deterministic tests for Google Lens search, zero-waste constraints, caching, and security."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "python"))

import config
from search.cache import get_cached_response, store_cached_response
from search.lens import (
    AuthenticationError,
    LensCandidate,
    QuotaExhaustedError,
    SearchError,
    parse_candidates,
    prepare_image_for_upload,
    resolve_public_image_url,
    search_google_lens,
    upload_image_to_serpapi,
)
from search.security import SecurityError, validate_public_url


class TestSearchSecurity(unittest.TestCase):
    def test_blocks_localhost_and_loopback(self):
        with self.assertRaises(SecurityError):
            validate_public_url("http://localhost:8080/image.jpg")
        with self.assertRaises(SecurityError):
            validate_public_url("http://127.0.0.1/face.png")

    def test_blocks_private_ip_networks(self):
        with self.assertRaises(SecurityError):
            validate_public_url("http://192.168.1.10/private.jpg")
        with self.assertRaises(SecurityError):
            validate_public_url("http://10.0.0.5/secret.jpg")
        with self.assertRaises(SecurityError):
            validate_public_url("http://172.16.0.1/admin.jpg")

    def test_blocks_cloud_metadata(self):
        with self.assertRaises(SecurityError):
            validate_public_url("http://169.254.169.254/latest/meta-data/")

    def test_blocks_non_http_schemes(self):
        with self.assertRaises(SecurityError):
            validate_public_url("file:///etc/passwd")
        with self.assertRaises(SecurityError):
            validate_public_url("ftp://example.com/image.jpg")


class TestSearchApiKeyHandling(unittest.TestCase):
    @patch.object(config, "SERPAPI_KEY", "")
    def test_missing_api_key_raises_clear_error_without_calling_network(self):
        with self.assertRaises(SearchError) as ctx:
            search_google_lens("https://example.com/photo.jpg")
        self.assertIn("SERPAPI_KEY is not configured", str(ctx.exception))

    @patch.object(config, "SERPAPI_KEY", "dummy_test_key")
    @patch("search.lens.requests.get")
    def test_authentication_error_on_401(self, mock_get):
        resp = MagicMock()
        resp.status_code = 401
        mock_get.return_value = resp

        with self.assertRaises(AuthenticationError) as ctx:
            search_google_lens("https://example.com/photo.jpg", force_refresh=True)
        self.assertIn("authentication failed", str(ctx.exception).lower())

    @patch.object(config, "SERPAPI_KEY", "dummy_test_key")
    @patch("search.lens.requests.get")
    def test_quota_exhaustion_on_429(self, mock_get):
        resp = MagicMock()
        resp.status_code = 429
        mock_get.return_value = resp

        with self.assertRaises(QuotaExhaustedError) as ctx:
            search_google_lens("https://example.com/photo.jpg", force_refresh=True)
        self.assertIn("quota", str(ctx.exception).lower())

    @patch.object(config, "SERPAPI_KEY", "dummy_test_key")
    @patch("search.lens.requests.get")
    def test_quota_error_in_json_body(self, mock_get):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"error": "Your monthly search quota has run out"}
        mock_get.return_value = resp

        with self.assertRaises(QuotaExhaustedError) as ctx:
            search_google_lens("https://example.com/photo.jpg", force_refresh=True)
        self.assertIn("quota", str(ctx.exception).lower())


class TestSearchCandidateParsingAndDeduplication(unittest.TestCase):
    def test_parse_candidates_deduplicates_and_normalizes(self):
        fixture = {
            "exact_matches": [
                {
                    "position": 1,
                    "title": "Exact Match Title",
                    "link": "https://example.com/page1",
                    "image": "https://example.com/img1.jpg",
                    "source": "example.com",
                },
                # Duplicate URL
                {
                    "position": 2,
                    "title": "Exact Match Duplicate",
                    "link": "https://example.com/page1",
                    "image": "https://example.com/img1.jpg",
                },
            ],
            "visual_matches": [
                {
                    "position": 1,
                    "title": "Visual Match Title",
                    "link": "https://news.example.com/article",
                    "thumbnail": "https://news.example.com/thumb.jpg",
                    "source": "news.example.com",
                }
            ],
        }

        candidates = parse_candidates(fixture, limit=10)
        self.assertEqual(len(candidates), 2)
        self.assertEqual(candidates[0].candidate_id, "exact_matches-1")
        self.assertEqual(candidates[0].source_url, "https://example.com/page1")
        self.assertEqual(candidates[0].image_url, "https://example.com/img1.jpg")
        self.assertEqual(candidates[1].candidate_id, "visual_matches-1")
        self.assertEqual(candidates[1].domain, "news.example.com")


class TestSearchCachingAndZeroWaste(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_cache_stores_and_retrieves_payload(self):
        payload = {"visual_matches": [{"link": "https://example.com/item", "image": "https://example.com/i.jpg"}]}
        store_cached_response("https://example.com/test.jpg", "all", 20, payload, cache_dir=self.tmp_dir)

        hit = get_cached_response("https://example.com/test.jpg", "all", 20, ttl_seconds=3600, cache_dir=self.tmp_dir)
        self.assertIsNotNone(hit)
        self.assertEqual(hit, payload)

    def test_cache_invalidates_on_different_search_params(self):
        payload = {"visual_matches": []}
        store_cached_response("https://example.com/test.jpg", "visual_matches", 10, payload, cache_dir=self.tmp_dir)

        # Different limit
        miss = get_cached_response("https://example.com/test.jpg", "visual_matches", 20, ttl_seconds=3600, cache_dir=self.tmp_dir)
        self.assertIsNone(miss)

    @patch.object(config, "SERPAPI_KEY", "dummy_key")
    @patch("search.lens.get_cached_response")
    @patch("search.lens.requests.get")
    def test_cache_hit_does_not_make_http_request(self, mock_get, mock_cache):
        mock_cache.return_value = {
            "visual_matches": [
                {"link": "https://example.com/page", "image": "https://example.com/face.jpg"}
            ]
        }
        candidates = search_google_lens("https://example.com/input.jpg")
        self.assertEqual(len(candidates), 1)
        mock_get.assert_not_called()

    def test_dry_run_validates_without_calling_network(self):
        # Even without an API key, dry-run succeeds validation
        candidates = search_google_lens("https://example.com/test.jpg", dry_run=True)
        self.assertEqual(candidates, [])


    def test_parse_candidates_handles_empty_matches_without_mock_substitution(self):
        fixture = {"visual_matches": [], "exact_matches": []}
        candidates = parse_candidates(fixture)
        self.assertEqual(candidates, [])

    def test_parse_candidates_preserves_distinct_source_urls(self):
        fixture = {
            "visual_matches": [
                {
                    "title": "Page A",
                    "link": "https://example.com/story-1",
                    "thumbnail": "https://cdn.example.com/photo.jpg",
                },
                {
                    "title": "Page B",
                    "link": "https://another.com/story-2",
                    "thumbnail": "https://cdn.example.com/photo.jpg",
                },
            ]
        }
        candidates = parse_candidates(fixture)
        self.assertEqual(len(candidates), 2)
        self.assertEqual(candidates[0].source_url, "https://example.com/story-1")
        self.assertEqual(candidates[1].source_url, "https://another.com/story-2")
        self.assertEqual(candidates[0].image_url, "https://cdn.example.com/photo.jpg")

    def test_parse_candidates_handles_missing_fields_gracefully(self):
        fixture = {
            "visual_matches": [
                {"title": None, "url": "https://news.example.com/article"},
                {"broken": "data"},
                {"image": "https://cdn.example.com/only-image.jpg"},
            ]
        }
        candidates = parse_candidates(fixture)
        self.assertEqual(len(candidates), 2)
        self.assertEqual(candidates[0].title, "")
        self.assertEqual(candidates[0].source_url, "https://news.example.com/article")
        self.assertEqual(candidates[1].image_url, "https://cdn.example.com/only-image.jpg")


class TestImagePreparation(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_valid_png_under_500kb(self):
        from io import BytesIO
        from PIL import Image

        buf = BytesIO()
        Image.new("RGB", (100, 100), color="blue").save(buf, format="PNG")
        data, mime, filename = prepare_image_for_upload(buf.getvalue(), filename="test.png")
        self.assertEqual(mime, "image/png")
        self.assertTrue(filename.endswith(".png"))
        self.assertLessEqual(len(data), 500 * 1024)

    def test_valid_jpeg_under_500kb(self):
        from io import BytesIO
        from PIL import Image

        buf = BytesIO()
        Image.new("RGB", (100, 100), color="red").save(buf, format="JPEG")
        data, mime, filename = prepare_image_for_upload(buf.getvalue(), filename="test.jpg")
        self.assertEqual(mime, "image/jpeg")
        self.assertTrue(filename.endswith(".jpg"))
        self.assertLessEqual(len(data), 500 * 1024)

    def test_valid_webp_under_500kb(self):
        from io import BytesIO
        from PIL import Image

        buf = BytesIO()
        Image.new("RGB", (100, 100), color="green").save(buf, format="WEBP")
        data, mime, filename = prepare_image_for_upload(buf.getvalue(), filename="test.webp")
        self.assertEqual(mime, "image/webp")
        self.assertTrue(filename.endswith(".webp"))
        self.assertLessEqual(len(data), 500 * 1024)

    def test_oversized_image_resized_preserving_aspect_ratio(self):
        from io import BytesIO
        import numpy as np
        from PIL import Image

        # Create a large 2000 x 1000 image (exact 2.0 aspect ratio) with random noise to ensure > 500 KB
        rng = np.random.default_rng(42)
        noise = rng.integers(0, 256, (1000, 2000, 3), dtype=np.uint8)
        img = Image.fromarray(noise, "RGB")
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=95)
        raw_bytes = buf.getvalue()
        self.assertGreater(len(raw_bytes), 500 * 1024)

        data, mime, filename = prepare_image_for_upload(raw_bytes, filename="large.jpg")
        self.assertLessEqual(len(data), 500 * 1024)

        with Image.open(BytesIO(data)) as resized_img:
            ratio = resized_img.width / resized_img.height
            self.assertAlmostEqual(ratio, 2.0, delta=0.05)

    def test_unsupported_format_rejected(self):
        from io import BytesIO
        from PIL import Image

        buf = BytesIO()
        Image.new("RGB", (50, 50)).save(buf, format="GIF")
        with self.assertRaises(SearchError) as ctx:
            prepare_image_for_upload(buf.getvalue(), filename="test.gif")
        self.assertIn("Unsupported image format", str(ctx.exception))

    def test_missing_file_raises_search_error(self):
        with self.assertRaises(SearchError):
            prepare_image_for_upload(self.tmp_dir / "nonexistent.jpg")


class TestSerpApiImageUpload(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp())
        self.test_img = self.tmp_dir / "test.jpg"
        from PIL import Image
        Image.new("RGB", (100, 100)).save(self.test_img, format="JPEG")

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    @patch.object(config, "SERPAPI_KEY", "")
    def test_missing_api_key_raises_auth_error(self):
        with self.assertRaises(AuthenticationError) as ctx:
            upload_image_to_serpapi(self.test_img)
        self.assertIn("SERPAPI_KEY is not configured", str(ctx.exception))

    @patch.object(config, "SERPAPI_KEY", "test_key")
    @patch("search.lens.requests.post")
    def test_successful_upload_returns_image_id(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"image_id": "temp_image_id_abc123"}
        mock_post.return_value = mock_resp

        image_id = upload_image_to_serpapi(self.test_img)
        self.assertEqual(image_id, "temp_image_id_abc123")

        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args[1]
        self.assertEqual(call_kwargs["data"]["api_key"], "test_key")
        self.assertIn("image", call_kwargs["files"])

    @patch.object(config, "SERPAPI_KEY", "test_key")
    @patch("search.lens.requests.post")
    def test_upload_auth_error_on_401(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_post.return_value = mock_resp

        with self.assertRaises(AuthenticationError):
            upload_image_to_serpapi(self.test_img)

    @patch.object(config, "SERPAPI_KEY", "test_key")
    @patch("search.lens.requests.post")
    def test_upload_quota_error_on_429(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_post.return_value = mock_resp

        with self.assertRaises(QuotaExhaustedError):
            upload_image_to_serpapi(self.test_img)

    @patch.object(config, "SERPAPI_KEY", "test_key")
    @patch("search.lens.requests.post")
    def test_upload_malformed_response_raises_error(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"status": "ok"}  # missing image_id
        mock_post.return_value = mock_resp

        with self.assertRaises(SearchError) as ctx:
            upload_image_to_serpapi(self.test_img)
        self.assertIn("did not return an image_id", str(ctx.exception))


class TestGoogleLensWithImageIdAndLocalPath(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp())
        self.test_img = self.tmp_dir / "test.jpg"
        from PIL import Image
        Image.new("RGB", (100, 100)).save(self.test_img, format="JPEG")

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    @patch.object(config, "SERPAPI_KEY", "test_key")
    @patch("search.lens.requests.get")
    def test_search_with_image_id_passes_param(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"visual_matches": []}
        mock_get.return_value = mock_resp

        candidates = search_google_lens(image_id="uploaded_id_999", force_refresh=True)
        self.assertEqual(candidates, [])

        mock_get.assert_called_once()
        params = mock_get.call_args[1]["params"]
        self.assertEqual(params["image_id"], "uploaded_id_999")
        self.assertNotIn("url", params)

    @patch.object(config, "SERPAPI_KEY", "test_key")
    @patch("search.lens.upload_image_to_serpapi")
    @patch("search.lens.requests.get")
    def test_search_with_image_path_uploads_and_queries(self, mock_get, mock_upload):
        mock_upload.return_value = "generated_img_id_777"
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "visual_matches": [
                {
                    "title": "NASA Match",
                    "link": "https://nasa.gov/news",
                    "thumbnail": "https://nasa.gov/thumb.jpg",
                }
            ]
        }
        mock_get.return_value = mock_resp

        candidates = search_google_lens(image_path=self.test_img, force_refresh=True)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].source_url, "https://nasa.gov/news")

        mock_upload.assert_called_once_with(self.test_img, api_key="test_key")
        params = mock_get.call_args[1]["params"]
        self.assertEqual(params["image_id"], "generated_img_id_777")


class TestSourceLinkHandlingAndIntegrity(unittest.TestCase):
    def test_candidate_source_page_url_preserved_distinct_from_thumbnail(self):
        fixture = {
            "visual_matches": [
                {
                    "position": 1,
                    "title": "Sunita Williams Space Station",
                    "link": "https://www.nasa.gov/astronauts/sunita-williams",
                    "thumbnail": "https://images-assets.nasa.gov/image/iss033e007883/thumb.jpg",
                    "source": "nasa.gov",
                }
            ]
        }
        candidates = parse_candidates(fixture)
        self.assertEqual(len(candidates), 1)
        candidate = candidates[0]
        # Preserved as source-page URL
        self.assertEqual(candidate.source_url, "https://www.nasa.gov/astronauts/sunita-williams")
        # Distinct thumbnail URL
        self.assertEqual(candidate.image_url, "https://images-assets.nasa.gov/image/iss033e007883/thumb.jpg")
        self.assertNotEqual(candidate.source_url, candidate.image_url)

    def test_empty_provider_response_is_honest_empty(self):
        fixture = {"visual_matches": [], "exact_matches": []}
        candidates = parse_candidates(fixture)
        self.assertEqual(candidates, [])

    def test_reddit_url_fixture_never_injected_in_real_results(self):
        fixture = {
            "visual_matches": [
                {
                    "title": "Example News",
                    "link": "https://example.com/article",
                    "image": "https://example.com/pic.jpg",
                }
            ]
        }
        candidates = parse_candidates(fixture)
        self.assertEqual(len(candidates), 1)
        self.assertNotIn("reddit.com", candidates[0].source_url)
        self.assertNotIn("reddit.com", candidates[0].image_url)


if __name__ == "__main__":
    unittest.main()

