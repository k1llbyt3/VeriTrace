"""Cosine similarity between ArcFace embeddings.

Cosine similarity measures the angle between two embedding vectors:
1.0 = identical direction, 0.0 = unrelated, negative = opposite.
Higher generally means the two faces look more alike to the model - it is
statistical evidence, never proof of a person's legal identity.
"""
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class SimilarityResult:
    """Similarity score and the decision made with a configured threshold."""

    index: int
    score: float
    passes_threshold: bool


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity of two vectors, safe for non-normalised input."""
    a = np.asarray(a, dtype=np.float32).reshape(-1)
    b = np.asarray(b, dtype=np.float32).reshape(-1)
    if a.shape != b.shape:
        raise ValueError(f"embedding size mismatch: {a.shape} vs {b.shape}")
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)


def passes_threshold(score: float, threshold: float) -> bool:
    """Return whether a similarity score qualifies at the configured cutoff."""
    return score >= threshold


def rank_similarities(
    reference: np.ndarray,
    candidates: list[np.ndarray],
    threshold: float,
) -> list[SimilarityResult]:
    """Rank candidate embeddings by cosine similarity, highest first."""
    results = [
        SimilarityResult(
            index=index,
            score=cosine_similarity(reference, candidate),
            passes_threshold=False,
        )
        for index, candidate in enumerate(candidates)
    ]
    ranked = sorted(results, key=lambda result: (-result.score, result.index))
    return [
        SimilarityResult(result.index, result.score, passes_threshold(result.score, threshold))
        for result in ranked
    ]


def best_similarity(reference: np.ndarray, candidates: list[np.ndarray]) -> tuple[float, int]:
    """Highest similarity between `reference` and any candidate face.

    Returns (score, index). Returns (-1.0, -1) when there are no candidates.
    A candidate image with several faces is judged by its best-matching face.
    """
    best_score, best_index = -1.0, -1
    for index, candidate in enumerate(candidates):
        score = cosine_similarity(reference, candidate)
        if score > best_score:
            best_score, best_index = score, index
    return best_score, best_index
