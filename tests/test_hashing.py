"""Focused byte-identity tests for evidence hashing and verification decisions."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "python"))

from evidence.hashing import hashes_match, sha256_bytes, sha256_file, to_bytes32


class HashingTests(unittest.TestCase):
    def test_sha256_is_deterministic_and_formats_as_bytes32(self):
        digest = sha256_bytes(b"exact artifact bytes")
        self.assertEqual(digest, sha256_bytes(b"exact artifact bytes"))
        self.assertEqual(to_bytes32(digest), "0x" + digest)

    def test_same_file_bytes_verify_successfully(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact = Path(directory) / "artifact.bin"
            artifact.write_bytes(b"preserved candidate bytes")
            registered = sha256_file(artifact)
            self.assertTrue(hashes_match(to_bytes32(registered), sha256_file(artifact)))

    def test_one_byte_change_verifies_as_failed(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact = Path(directory) / "artifact.bin"
            artifact.write_bytes(b"preserved candidate bytes")
            registered = sha256_file(artifact)
            artifact.write_bytes(b"preserved candidate byteS")
            self.assertFalse(hashes_match(registered, sha256_file(artifact)))


if __name__ == "__main__":
    unittest.main()
