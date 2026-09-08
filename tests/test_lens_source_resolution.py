import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "python"))

from search.lens import resolve_public_image_url


class TestPublicImageSourceResolution(unittest.TestCase):
    @patch("search.lens.requests.get")
    def test_resolves_open_graph_image_from_public_post(self, mock_get):
        response = Mock()
        response.text = '<html><meta property="og:image" content="https://cdn.example.com/photo.webp"></html>'
        response.raise_for_status.return_value = None
        mock_get.return_value = response

        resolved = resolve_public_image_url("https://www.instagram.com/p/example/")

        self.assertEqual(resolved, "https://cdn.example.com/photo.webp")
        mock_get.assert_called_once()


if __name__ == "__main__":
    unittest.main()