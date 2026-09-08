"""Central configuration.

Everything tunable lives in the project's `.env` file and is read here once,
so no module ever hardcodes a key, URL or threshold.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# project root = the folder that contains `python/`, `blockchain/`, `.env`
ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

ARTIFACTS_DIR = ROOT / "artifacts"
SAMPLES_DIR = ROOT / "samples"
BLOCKCHAIN_DIR = ROOT / "blockchain"


def _str(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def _int(name: str, default: int) -> int:
    raw = _str(name)
    return int(raw) if raw else default


def _float(name: str, default: float) -> float:
    raw = _str(name)
    return float(raw) if raw else default


# --- search ---
SERPAPI_KEY = _str("SERPAPI_KEY")

# --- face pipeline ---
INSIGHTFACE_MODEL = _str("INSIGHTFACE_MODEL", "buffalo_l")
DET_SIZE = _int("DET_SIZE", 640)
# Empirical demo cutoff, NOT a scientific constant. See docs/LIMITATIONS.md.
FACE_SIMILARITY_THRESHOLD = _float("FACE_SIMILARITY_THRESHOLD", 0.40)
MAX_CANDIDATES = _int("MAX_CANDIDATES", 20)

# --- blockchain ---
RPC_URL = _str("RPC_URL", "http://127.0.0.1:8545")
PRIVATE_KEY = _str("PRIVATE_KEY")
CONTRACT_ADDRESS = _str("CONTRACT_ADDRESS")
CHAIN_ID = _int("CHAIN_ID", 31337)
