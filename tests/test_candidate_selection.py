"""Tests for the Selected Candidate Integration pipeline.

Three focused test scenarios:
  1. Qualifying candidate selection — a candidate passes the threshold and is selected
  2. No candidate passing threshold — all candidates are below the threshold
  3. Inaccessible/invalid candidate handling — downloads fail or produce no face

All tests mock the network layer (SerpApi + image downloads) and the face engine
so they run instantly, deterministically, and without API keys. The pipeline
logic itself is exercised for real.
"""
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np

# Make sure project root python/ is on the path so imports resolve
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "python"))

from face.engine import FaceRecord
from search.lens import LensCandidate
from search.downloader import DownloadError


def _make_candidate(cid, title="Test", image_url="https://example.com/face.jpg",
                    source_url="https://example.com/page", domain="example.com",
                    search_type="visual_matches", search_rank=1):
    return LensCandidate(
        candidate_id=cid,
        title=title,
        source_url=source_url,
        image_url=image_url,
        domain=domain,
        search_type=search_type,
        search_rank=search_rank,
    )


def _face_record(embedding_vector, det_score=0.99, index=0):
    """Build a FaceRecord with a known embedding."""
    emb = np.array(embedding_vector, dtype=np.float32)
    norm = float(np.linalg.norm(emb))
    if norm > 0:
        emb = emb / norm
    return FaceRecord(
        index=index,
        bbox=[0.0, 0.0, 100.0, 100.0],
        det_score=det_score,
        embedding=emb,
    )


class TestQualifyingCandidateSelection(unittest.TestCase):
    """Scenario 1: At least one candidate qualifies and the best one is selected."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        # Write a tiny dummy image for the reference
        self.input_img = self.tmpdir / "input.jpg"
        self.input_img.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    @patch("pipeline.config")
    @patch("pipeline.download_image")
    @patch("pipeline.load_image")
    def test_selects_highest_qualifying_candidate(self, mock_load, mock_download, mock_config):
        """Two candidates qualify; the one with higher similarity wins."""
        mock_config.ARTIFACTS_DIR = self.tmpdir
        mock_config.FACE_SIMILARITY_THRESHOLD = 0.40
        mock_config.MAX_CANDIDATES = 20

        # Reference embedding: unit vector along axis 0
        ref_embedding = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        ref_face = _face_record([1.0, 0.0, 0.0])

        # Candidate A: similarity ~0.6 (qualifies at 0.40)
        face_a = _face_record([0.6, 0.8, 0.0])
        # Candidate B: similarity ~0.95 (qualifies at 0.40, HIGHER)
        face_b = _face_record([0.95, 0.1, 0.0])
        # Candidate C: similarity ~0.2 (does NOT qualify)
        face_c = _face_record([0.2, 0.0, 0.98])

        candidates = [
            _make_candidate("vm-1", title="Low match", search_rank=1),
            _make_candidate("vm-2", title="Best match", search_rank=2,
                            image_url="https://example.com/best.jpg"),
            _make_candidate("vm-3", title="Below threshold", search_rank=3,
                            image_url="https://example.com/low.jpg"),
        ]

        # download_image just writes dummy bytes
        def fake_download(url, dest):
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 50)
            return 54

        mock_download.side_effect = fake_download
        mock_load.return_value = np.zeros((100, 100, 3), dtype=np.uint8)

        # Build a mock engine
        mock_engine = MagicMock()
        mock_engine.analyse_file.return_value = [ref_face]
        # Each call to analyse_image returns the face for that candidate
        mock_engine.analyse_image.side_effect = [[face_a], [face_b], [face_c]]

        from pipeline import select_candidate
        result = select_candidate(
            input_image=str(self.input_img),
            case_id="test-case",
            threshold=0.40,
            engine=mock_engine,
            candidates=candidates,
        )

        # --- assertions ---
        self.assertTrue(result.has_selection)
        self.assertEqual(result.selected.candidate.candidate_id, "vm-2")
        self.assertEqual(result.selected.candidate.title, "Best match")
        self.assertGreater(result.selected.best_face_similarity, 0.90)
        self.assertTrue(result.selected.qualifies)
        self.assertEqual(result.qualifying, 2)  # A and B qualify, C does not
        self.assertEqual(result.evaluated, 3)

        # Metadata file was written
        meta_path = self.tmpdir / "test-case" / "selection_metadata.json"
        self.assertTrue(meta_path.is_file())
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        self.assertIsNotNone(meta["selected"])
        self.assertEqual(meta["selected"]["candidate_id"], "vm-2")


class TestNoCandidatePassesThreshold(unittest.TestCase):
    """Scenario 2: All candidates are below threshold."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.input_img = self.tmpdir / "input.jpg"
        self.input_img.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    @patch("pipeline.config")
    @patch("pipeline.download_image")
    @patch("pipeline.load_image")
    def test_reports_no_selection_when_all_below_threshold(self, mock_load, mock_download, mock_config):
        mock_config.ARTIFACTS_DIR = self.tmpdir
        mock_config.FACE_SIMILARITY_THRESHOLD = 0.90
        mock_config.MAX_CANDIDATES = 20

        ref_face = _face_record([1.0, 0.0, 0.0])
        # Both faces are far from reference
        face_a = _face_record([0.0, 1.0, 0.0])  # similarity ~0
        face_b = _face_record([0.3, 0.7, 0.0])  # similarity ~0.39

        candidates = [
            _make_candidate("vm-1", title="Wrong person A"),
            _make_candidate("vm-2", title="Wrong person B",
                            image_url="https://example.com/b.jpg"),
        ]

        def fake_download(url, dest):
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 50)
            return 54

        mock_download.side_effect = fake_download
        mock_load.return_value = np.zeros((100, 100, 3), dtype=np.uint8)

        mock_engine = MagicMock()
        mock_engine.analyse_file.return_value = [ref_face]
        mock_engine.analyse_image.side_effect = [[face_a], [face_b]]

        from pipeline import select_candidate
        result = select_candidate(
            input_image=str(self.input_img),
            case_id="test-no-match",
            threshold=0.90,
            engine=mock_engine,
            candidates=candidates,
        )

        self.assertFalse(result.has_selection)
        self.assertIsNone(result.selected)
        self.assertEqual(result.qualifying, 0)
        self.assertEqual(result.evaluated, 2)
        self.assertEqual(result.total_candidates, 2)

        # Metadata still written, but selected is None
        meta_path = self.tmpdir / "test-no-match" / "selection_metadata.json"
        self.assertTrue(meta_path.is_file())
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        self.assertIsNone(meta["selected"])


class TestInaccessibleInvalidCandidateHandling(unittest.TestCase):
    """Scenario 3: Some candidates fail to download or have no face."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.input_img = self.tmpdir / "input.jpg"
        self.input_img.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    @patch("pipeline.config")
    @patch("pipeline.download_image")
    @patch("pipeline.load_image")
    def test_skips_bad_candidates_selects_good_one(self, mock_load, mock_download, mock_config):
        """
        Candidate 1: download fails (network error)
        Candidate 2: downloads OK but no face detected
        Candidate 3: downloads OK, has face, qualifies — should be selected
        Candidate 4: no image URL at all
        """
        mock_config.ARTIFACTS_DIR = self.tmpdir
        mock_config.FACE_SIMILARITY_THRESHOLD = 0.40
        mock_config.MAX_CANDIDATES = 20

        ref_face = _face_record([1.0, 0.0, 0.0])
        good_face = _face_record([0.9, 0.1, 0.0])  # high similarity

        candidates = [
            _make_candidate("vm-1", title="Download fails",
                            image_url="https://example.com/broken.jpg"),
            _make_candidate("vm-2", title="No face in image",
                            image_url="https://example.com/landscape.jpg"),
            _make_candidate("vm-3", title="Good candidate",
                            image_url="https://example.com/good.jpg"),
            _make_candidate("vm-4", title="No image URL", image_url=""),
        ]

        call_count = [0]

        def fake_download(url, dest):
            call_count[0] += 1
            if "broken" in url:
                raise DownloadError("connection refused")
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 50)
            return 54

        mock_download.side_effect = fake_download
        mock_load.return_value = np.zeros((100, 100, 3), dtype=np.uint8)

        mock_engine = MagicMock()
        mock_engine.analyse_file.return_value = [ref_face]
        # Call order for analyse_image: candidate 2 (no face) then candidate 3 (good face)
        # Candidate 1 fails download, candidate 4 has no URL — neither reaches analyse_image
        mock_engine.analyse_image.side_effect = [[], [good_face]]

        from pipeline import select_candidate
        result = select_candidate(
            input_image=str(self.input_img),
            case_id="test-mixed",
            threshold=0.40,
            engine=mock_engine,
            candidates=candidates,
        )

        # Pipeline did not crash
        self.assertTrue(result.has_selection)
        self.assertEqual(result.selected.candidate.candidate_id, "vm-3")
        self.assertEqual(result.selected.candidate.title, "Good candidate")
        self.assertTrue(result.selected.qualifies)
        self.assertGreater(result.selected.best_face_similarity, 0.40)

        # The failed candidates are recorded with errors
        by_id = {cr.candidate.candidate_id: cr for cr in result.all_results}
        self.assertFalse(by_id["vm-1"].downloaded)
        self.assertIn("connection refused", by_id["vm-1"].error)

        self.assertTrue(by_id["vm-2"].downloaded)
        self.assertFalse(by_id["vm-2"].has_face)
        self.assertIn("no face", by_id["vm-2"].error)

        self.assertFalse(by_id["vm-4"].downloaded)
        self.assertIn("no image URL", by_id["vm-4"].error)

        # 2 successfully downloaded (landscape + good), 1 qualifying
        self.assertEqual(result.evaluated, 2)
        self.assertEqual(result.qualifying, 1)
        self.assertEqual(result.total_candidates, 4)

    @patch("pipeline.config")
    @patch("pipeline.download_image")
    @patch("pipeline.load_image")
    def test_all_candidates_inaccessible_returns_no_selection(self, mock_load, mock_download, mock_config):
        """When every single candidate fails, the pipeline still completes."""
        mock_config.ARTIFACTS_DIR = self.tmpdir
        mock_config.FACE_SIMILARITY_THRESHOLD = 0.40
        mock_config.MAX_CANDIDATES = 20

        ref_face = _face_record([1.0, 0.0, 0.0])

        candidates = [
            _make_candidate("vm-1", title="Fails", image_url="https://example.com/a.jpg"),
            _make_candidate("vm-2", title="Also fails", image_url="https://example.com/b.jpg"),
        ]

        mock_download.side_effect = DownloadError("network timeout")
        mock_load.return_value = np.zeros((100, 100, 3), dtype=np.uint8)

        mock_engine = MagicMock()
        mock_engine.analyse_file.return_value = [ref_face]

        from pipeline import select_candidate
        result = select_candidate(
            input_image=str(self.input_img),
            case_id="test-all-fail",
            threshold=0.40,
            engine=mock_engine,
            candidates=candidates,
        )

        self.assertFalse(result.has_selection)
        self.assertIsNone(result.selected)
        self.assertEqual(result.evaluated, 0)
        self.assertEqual(result.qualifying, 0)
        self.assertEqual(len(result.all_results), 2)
        for cr in result.all_results:
            self.assertIsNotNone(cr.error)


class TestEmptyCandidateList(unittest.TestCase):
    """Edge case: Lens returns zero candidates."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.input_img = self.tmpdir / "input.jpg"
        self.input_img.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    @patch("pipeline.config")
    @patch("pipeline.search_google_lens", return_value=[])
    def test_empty_search_results_return_no_public_matches(self, mock_search, mock_config):
        mock_config.ARTIFACTS_DIR = self.tmpdir
        mock_config.FACE_SIMILARITY_THRESHOLD = 0.40
        mock_config.MAX_CANDIDATES = 20
        case_dir = self.tmpdir / "test-empty"
        case_dir.mkdir()
        (case_dir / "metadata.json").write_text(
            json.dumps({"input": {"source_url": "https://example.com/input.jpg"}}),
            encoding="utf-8",
        )

        mock_engine = MagicMock()
        ref_face = _face_record([1.0, 0.0, 0.0])
        mock_engine.analyse_file.return_value = [ref_face]

        from pipeline import select_candidate
        result = select_candidate(
            input_image=str(self.input_img),
            case_id="test-empty",
            threshold=0.40,
            engine=mock_engine,
        )

        self.assertFalse(result.has_selection)
        self.assertEqual(result.total_candidates, 0)
        self.assertEqual(len(result.all_results), 0)
        self.assertEqual(result.message, "No public matches found")
        mock_search.assert_called_once()
        self.assertTrue((self.tmpdir / "test-empty" / "selection_metadata.json").is_file())


if __name__ == "__main__":
    unittest.main()
