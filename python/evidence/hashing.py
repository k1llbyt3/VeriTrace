"""SHA-256 fingerprinting of the EXACT bytes of a file.

SHA-256 answers one question only: "are these bytes byte-for-byte identical?"
It is not a visual comparison - re-saving, resizing, re-compressing or editing
metadata changes the hash even when the picture looks the same to a human.
That is why the pipeline preserves the exact downloaded artifact and hashes it
without touching it.
"""
from datetime import datetime, timezone
from pathlib import Path
import hashlib

CHUNK_SIZE = 1024 * 1024  # read 1 MB at a time so huge files never blow up RAM


def sha256_bytes(data: bytes) -> str:
    """SHA-256 hex digest of an in-memory byte string."""
    return hashlib.sha256(data).hexdigest()


def sha256_file(path) -> str:
    """SHA-256 hex digest of a file's exact bytes.

    Raises FileNotFoundError / IsADirectoryError for unusable paths.
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"not a readable file: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def to_bytes32(hex_digest: str) -> str:
    """Format a 64-char hex digest as a Solidity `bytes32` literal (0x-prefixed)."""
    clean = hex_digest.lower().removeprefix("0x")
    if len(clean) != 64 or any(c not in "0123456789abcdef" for c in clean):
        raise ValueError(f"not a SHA-256 hex digest: {hex_digest!r}")
    return "0x" + clean


def hashes_match(expected: str, actual: str) -> bool:
    """Return whether two SHA-256 values name the same exact bytes.

    The function accepts either normal hexadecimal digests or Solidity's
    ``0x``-prefixed ``bytes32`` representation.  It deliberately makes no
    visual-image comparison: a match is only a byte-for-byte match.
    """
    return expected.lower().removeprefix("0x") == actual.lower().removeprefix("0x")


def hash_report(path) -> dict:
    """Everything we want to show/record about one hashed artifact."""
    path = Path(path)
    digest = sha256_file(path)
    return {
        "algorithm": "SHA-256",
        "file": str(path),
        "filename": path.name,
        "size_bytes": path.stat().st_size,
        "sha256": digest,
        "bytes32": to_bytes32(digest),
        "hashed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
