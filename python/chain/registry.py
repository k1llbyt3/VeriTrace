"""Bridge from Python to the ethers.js scripts in blockchain/scripts/.

The blockchain layer is JavaScript (ethers.js + Hardhat, as specified), so the
Python pipeline shells out to it and reads a single JSON object from stdout.
Node's progress messages go to stderr and are surfaced only on failure.
"""
import json
import shutil
import subprocess

import config


class ChainError(RuntimeError):
    """Any failure talking to the blockchain layer."""


def _run(script: str, args: list[str], timeout: int = 240) -> dict:
    node = shutil.which("node")
    if node is None:
        raise ChainError("Node.js not found on PATH - install Node 20+ and reopen the terminal")

    script_path = config.BLOCKCHAIN_DIR / "scripts" / script
    if not script_path.is_file():
        raise ChainError(f"missing blockchain script: {script_path}")

    try:
        process = subprocess.run(
            [node, str(script_path), *args],
            cwd=config.BLOCKCHAIN_DIR,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise ChainError(f"{script} timed out after {timeout}s") from exc

    lines = [line for line in process.stdout.splitlines() if line.strip()]
    if not lines:
        detail = process.stderr.strip() or f"exit code {process.returncode}"
        raise ChainError(f"{script} returned no result: {detail}")

    try:
        payload = json.loads(lines[-1])
    except json.JSONDecodeError as exc:
        raise ChainError(f"{script} returned unreadable output: {lines[-1][:200]}") from exc

    if not payload.get("ok"):
        raise ChainError(payload.get("error", "unknown blockchain error"))
    return payload


def register(content_hash: str, source_url: str = "") -> dict:
    """Write a SHA-256 fingerprint on-chain. Returns tx hash, block, gas, etc."""
    return _run("register.js", ["--hash", content_hash, "--url", source_url])


def fetch_by_tx(tx_hash: str) -> dict:
    """Read the fingerprint back out of a transaction's ContentRegistered event."""
    return _run("fetch.js", ["--tx", tx_hash])


def fetch_by_hash(content_hash: str) -> dict:
    """Read the stored record for a fingerprint straight from contract storage."""
    return _run("fetch.js", ["--hash", content_hash])
