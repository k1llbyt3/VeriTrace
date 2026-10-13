"""Regression tests for Windows console Unicode encoding safety and artifact resume."""
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "python"))

from main import cmd_select, configure_streams, safe_str
from pipeline import CandidateResult, LensCandidate, SelectionResult, _download_candidate, select_candidate


class TestUnicodeOutputSafety(unittest.TestCase):
    def test_safe_str_handles_unicode_and_ascii(self):
        # Hindi Devanagari (the exact title that triggered the crash)
        hindi = "तू जाने ना | Tu Jane Na Full Song | Atif Aslam ..."
        self.assertIsInstance(safe_str(hindi), str)
        self.assertIn("Tu Jane Na", safe_str(hindi))

        # Emojis and other Unicode scripts
        emoji = "Katrina Kaif 🌟 Portrait"
        self.assertIsInstance(safe_str(emoji), str)

        # None and empty
        self.assertEqual(safe_str(None), "")
        self.assertEqual(safe_str(""), "")

        # Pure ASCII
        ascii_text = "Simple ASCII Title"
        self.assertEqual(safe_str(ascii_text), "Simple ASCII Title")

    def test_configure_streams_does_not_crash(self):
        # Should execute safely on any environment
        configure_streams()

    @patch("pipeline.select_candidate")
    def test_cmd_select_prints_unicode_titles_without_crash(self, mock_select):
        cand1 = LensCandidate(
            candidate_id="vm-1",
            title="तू जाने ना | Tu Jane Na Full Song | Atif Aslam ...",
            source_url="https://youtube.com/watch?v=123",
            image_url="https://i.ytimg.com/vi/123/sddefault.jpg",
            domain="youtube.com",
            search_type="visual_matches",
            search_rank=1,
        )
        cand2 = LensCandidate(
            candidate_id="vm-2",
            title="",  # missing title
            source_url="https://example.com/item",
            image_url="https://example.com/pic.jpg",
            domain="",  # missing domain
            search_type="visual_matches",
            search_rank=2,
        )
        cr1 = CandidateResult(candidate=cand1, downloaded=True, local_path=Path("fake/path1.jpg"), size_bytes=100, best_face_similarity=0.95, qualifies=True)
        cr2 = CandidateResult(candidate=cand2, downloaded=True, local_path=Path("fake/path2.jpg"), size_bytes=200, best_face_similarity=0.20, qualifies=False)

        mock_result = SelectionResult(
            input_image="input.jpg",
            threshold=0.40,
            total_candidates=2,
            evaluated=2,
            qualifying=1,
            selected=cr1,
            all_results=[cr1, cr2],
            case_dir=Path("artifacts/case-test"),
        )
        mock_select.return_value = mock_result

        args = MagicMock()
        args.input_image = "input.jpg"
        args.case = "case-test"
        args.threshold = 0.40
        args.type = "all"
        args.limit = 10
        args.source_url = None
        args.refresh = False
        args.dry_run = False

        buf = io.StringIO()
        with patch("sys.stdout", buf):
            code = cmd_select(args)
        self.assertEqual(code, 0)
        output = buf.getvalue()
        self.assertIn("SELECTED CANDIDATE", output)
        self.assertIn("youtube.com", output)


class TestArtifactResumeWithoutNetwork(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp())
        self.input_img = self.tmp_dir / "input.jpg"
        self.input_img.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_download_candidate_reuses_local_file_without_network(self):
        cand = LensCandidate(
            candidate_id="vm-1",
            title="Local Candidate",
            source_url="https://example.com",
            image_url="https://example.com/photo.jpg",
            domain="example.com",
            search_type="visual_matches",
            search_rank=1,
        )
        local_cand = self.tmp_dir / "candidate-001.jpg"
        local_cand.write_bytes(b"existing_bytes_12345")

        with patch("pipeline.download_image") as mock_dl:
            dest, size = _download_candidate(cand, self.tmp_dir, 1)
            mock_dl.assert_not_called()
            self.assertEqual(dest, local_cand)
            self.assertEqual(size, len(b"existing_bytes_12345"))

    @patch("pipeline.config")
    @patch("pipeline.search_google_lens")
    @patch("pipeline.get_engine")
    def test_select_candidate_resumes_from_existing_selection_metadata(self, mock_engine_fn, mock_lens, mock_config):
        mock_config.ARTIFACTS_DIR = self.tmp_dir
        mock_config.FACE_SIMILARITY_THRESHOLD = 0.40
        mock_config.MAX_CANDIDATES = 20

        case_dir = self.tmp_dir / "case-resume"
        case_dir.mkdir()
        sel_meta = {
            "all_results": [
                {
                    "candidate_id": "vm-1",
                    "title": "Preserved Candidate Title",
                    "source_url": "https://example.com/story",
                    "image_url": "https://example.com/pic.jpg",
                    "domain": "example.com",
                    "search_type": "visual_matches",
                    "search_rank": 1,
                }
            ]
        }
        (case_dir / "selection_metadata.json").write_text(json.dumps(sel_meta), encoding="utf-8")
        from PIL import Image
        Image.new("RGB", (20, 20)).save(case_dir / "candidate-001.jpg", format="JPEG")

        import numpy as np
        from face.engine import FaceRecord

        ref_face = FaceRecord(index=0, bbox=[0, 0, 100, 100], det_score=0.99, embedding=np.array([1.0, 0.0, 0.0], dtype=np.float32))
        mock_engine = MagicMock()
        mock_engine.analyse_file.return_value = [ref_face]
        mock_engine.analyse_image.return_value = [ref_face]
        mock_engine_fn.return_value = mock_engine

        result = select_candidate(
            input_image=str(self.input_img),
            case_id="case-resume",
            threshold=0.40,
        )

        mock_lens.assert_not_called()
        self.assertEqual(result.total_candidates, 1)
        self.assertTrue(result.has_selection)
        self.assertEqual(result.selected.candidate.title, "Preserved Candidate Title")


if __name__ == "__main__":
    unittest.main()
