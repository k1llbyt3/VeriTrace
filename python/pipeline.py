"""Selected Candidate Integration pipeline.

Connects the existing stages into one end-to-end flow:

    SerpApi Google Lens
    → candidate results
    → candidate downloader
    → SCRFD/ArcFace face comparison
    → similarity ranking
    → configured threshold
    → select the highest qualifying candidate
    → preserve that selected artifact and its metadata.

Every step delegates to an existing module; nothing is duplicated here.
"""
import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import config
from face.engine import FaceEngine, InvalidImageError, get_engine, load_image
from face.similarity import best_similarity, passes_threshold
from search.downloader import DownloadError, download_image, _extension
from search.lens import LensCandidate, SearchError, resolve_public_image_url, search_google_lens

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures for pipeline results
# ---------------------------------------------------------------------------


@dataclass
class CandidateResult:
    """Outcome of evaluating one Lens candidate through the face pipeline."""

    candidate: LensCandidate
    downloaded: bool = False
    local_path: Optional[Path] = None
    size_bytes: int = 0
    has_face: bool = False
    best_face_similarity: float = -1.0
    qualifies: bool = False
    error: Optional[str] = None

    def as_dict(self) -> dict:
        d = {
            **self.candidate.as_dict(),
            "downloaded": self.downloaded,
            "local_path": str(self.local_path) if self.local_path else None,
            "size_bytes": self.size_bytes,
            "has_face": self.has_face,
            "best_face_similarity": self.best_face_similarity,
            "qualifies": self.qualifies,
        }
        if self.error:
            d["error"] = self.error
        return d


@dataclass
class SelectionResult:
    """Full outcome of the candidate selection pipeline."""

    input_image: str
    threshold: float
    total_candidates: int = 0
    evaluated: int = 0
    qualifying: int = 0
    selected: Optional[CandidateResult] = None
    all_results: list[CandidateResult] = field(default_factory=list)
    case_dir: Optional[Path] = None
    message: str = ""

    @property
    def has_selection(self) -> bool:
        return self.selected is not None


# ---------------------------------------------------------------------------
# Core pipeline
# ---------------------------------------------------------------------------


def _download_candidate(
    candidate: LensCandidate,
    case_dir: Path,
    index: int,
) -> tuple[Path, int]:
    """Download a single candidate image.  Returns (local_path, size_bytes).

    Raises DownloadError on any failure — callers catch and continue.
    """
    if not candidate.image_url:
        raise DownloadError(f"{candidate.candidate_id}: no image URL")
    ext = _extension(candidate.image_url, "", fallback=".jpg")
    filename = f"candidate-{index:03d}{ext}"
    dest = case_dir / filename
    if dest.is_file() and dest.stat().st_size > 0:
        return dest, dest.stat().st_size
    existing = list(case_dir.glob(f"candidate-{index:03d}.*"))
    if existing and existing[0].is_file() and existing[0].stat().st_size > 0:
        return existing[0], existing[0].stat().st_size
    size = download_image(candidate.image_url, dest)
    return dest, size


def _evaluate_candidate(
    engine: FaceEngine,
    reference_embeddings,
    candidate: LensCandidate,
    case_dir: Path,
    index: int,
    threshold: float,
) -> CandidateResult:
    """Download one candidate, detect faces, compute similarity, check threshold.

    Never raises — every error is captured in the returned CandidateResult so
    the pipeline keeps going through all candidates.
    """
    result = CandidateResult(candidate=candidate)
    # --- download ---
    try:
        local_path, size = _download_candidate(candidate, case_dir, index)
    except DownloadError as exc:
        result.error = str(exc)
        logger.info("Skip %s: %s", candidate.candidate_id, exc)
        return result

    result.downloaded = True
    result.local_path = local_path
    result.size_bytes = size

    # --- face detection + embedding ---
    try:
        image = load_image(local_path)
        faces = engine.analyse_image(image)
    except (InvalidImageError, Exception) as exc:  # noqa: BLE001
        result.error = f"face detection failed: {exc}"
        logger.info("Skip %s: %s", candidate.candidate_id, result.error)
        return result

    if not faces:
        result.error = "no face detected"
        logger.info("Skip %s: no face detected", candidate.candidate_id)
        return result

    result.has_face = True

    # --- similarity (reuse existing best_similarity) ---
    score = max(
        best_similarity(reference_embedding, [f.embedding for f in faces])[0]
        for reference_embedding in reference_embeddings
    )
    result.best_face_similarity = score
    result.qualifies = passes_threshold(score, threshold)
    return result


def select_candidate(
    input_image: str,
    case_id: str = "case-001",
    threshold: float | None = None,
    search_type: str = "visual_matches",
    limit: int | None = None,
    engine: FaceEngine | None = None,
    candidates: list[LensCandidate] | None = None,
    source_url: str | None = None,
    force_refresh: bool = False,
    dry_run: bool = False,
) -> SelectionResult:
    """Run the full candidate selection pipeline.

    Parameters
    ----------
    input_image : str
        Path to a local image containing the reference face.
    case_id : str
        Case directory name under ``config.ARTIFACTS_DIR``.
    threshold : float or None
        Override ``config.FACE_SIMILARITY_THRESHOLD`` if given.
    search_type : str
        Lens search type (``"visual_matches"``, ``"exact_matches"``, ``"all"``).
    limit : int or None
        Override ``config.MAX_CANDIDATES`` if given.
    engine : FaceEngine or None
        Pre-built engine (useful for tests). Falls back to ``get_engine()``.
    candidates : list[LensCandidate] or None
        Pre-fetched candidates (skip SerpApi call). Useful for tests and for
        pipelines that already have the Lens results.

    Returns
    -------
    SelectionResult
        Contains the selected candidate (if any), all individual results,
        and summary statistics.
    """
    threshold = threshold if threshold is not None else config.FACE_SIMILARITY_THRESHOLD
    limit = limit if limit is not None else config.MAX_CANDIDATES
    case_dir = config.ARTIFACTS_DIR / case_id

    result = SelectionResult(
        input_image=input_image,
        threshold=threshold,
        case_dir=case_dir,
    )

    # --- 1. Reference face embeddings ---
    if engine is None:
        engine = get_engine()
    try:
        reference_faces = engine.analyse_file(input_image)
    except Exception as exc:
        raise RuntimeError(f"Cannot process reference image: {exc}") from exc
    if not reference_faces:
        raise RuntimeError(f"Cannot process reference image: no face detected in {input_image}")
    reference_embeddings = [face.embedding for face in reference_faces]

    # --- 2. SerpApi Google Lens search (unless pre-provided) ---
    if candidates is None:
        meta_path = case_dir / "metadata.json"
        sel_meta_path = case_dir / "selection_metadata.json"
        case_dir.mkdir(parents=True, exist_ok=True)

        # Check if we can resume candidates from existing selection_metadata.json
        if not force_refresh and sel_meta_path.is_file():
            try:
                saved_meta = json.loads(sel_meta_path.read_text(encoding="utf-8"))
                saved_candidates = []
                for item in saved_meta.get("all_results", []):
                    c_info = item.get("candidate") if isinstance(item.get("candidate"), dict) else item
                    saved_candidates.append(
                        LensCandidate(
                            candidate_id=c_info.get("candidate_id") or "",
                            title=c_info.get("title") or "",
                            source_url=c_info.get("source_url") or "",
                            image_url=c_info.get("image_url") or "",
                            domain=c_info.get("domain") or "",
                            search_type=c_info.get("search_type") or "visual_matches",
                            search_rank=c_info.get("search_rank") or 1,
                        )
                    )
                if saved_candidates:
                    logger.info("Resuming candidate evaluation from %s (%d candidates)", sel_meta_path, len(saved_candidates))
                    candidates = saved_candidates
            except Exception as exc:
                logger.warning("Could not resume from %s: %s", sel_meta_path, exc)

        if candidates is None:
            if source_url:
                image_url = resolve_public_image_url(source_url)
                metadata = {
                    "input": {
                        "source_url": image_url,
                        "source_page_url": source_url,
                        "local_artifact_filename": Path(input_image).name,
                        "size_bytes": Path(input_image).stat().st_size if Path(input_image).is_file() else 0,
                    }
                }
                meta_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
                candidates = search_google_lens(
                    image_url=image_url,
                    search_type=search_type,
                    limit=limit,
                    force_refresh=force_refresh,
                    dry_run=dry_run,
                )
            elif meta_path.is_file() and json.loads(meta_path.read_text(encoding="utf-8")).get("input", {}).get("source_url"):
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                image_url = meta.get("input", {}).get("source_url", "")
                candidates = search_google_lens(
                    image_url=image_url,
                    search_type=search_type,
                    limit=limit,
                    force_refresh=force_refresh,
                    dry_run=dry_run,
                )
            elif Path(input_image).is_file():
                metadata = {
                    "input": {
                        "source_type": "local_upload",
                        "local_artifact_filename": Path(input_image).name,
                        "size_bytes": Path(input_image).stat().st_size,
                    }
                }
                meta_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
                candidates = search_google_lens(
                    image_path=input_image,
                    search_type=search_type,
                    limit=limit,
                    force_refresh=force_refresh,
                    dry_run=dry_run,
                )
            else:
                raise RuntimeError(
                    f"No public image URL and input image file does not exist: {input_image}"
                )

    if dry_run:
        result.message = "Dry-run validation successful. No API requests were sent to SerpApi."
        _write_selection_metadata(result, case_dir)
        return result

    result.total_candidates = len(candidates)
    if not candidates:
        result.message = "No public matches found"
        _write_selection_metadata(result, case_dir)
        return result

    # --- 3. Evaluate each candidate ---
    case_dir.mkdir(parents=True, exist_ok=True)
    for idx, candidate in enumerate(candidates, start=1):
        cr = _evaluate_candidate(
            engine, reference_embeddings, candidate, case_dir, idx, threshold
        )
        result.all_results.append(cr)

    result.evaluated = sum(1 for cr in result.all_results if cr.downloaded)
    result.qualifying = sum(1 for cr in result.all_results if cr.qualifies)

    # --- 4. Select the highest-ranked qualifying candidate ---
    qualifying = [cr for cr in result.all_results if cr.qualifies]
    if qualifying:
        # Highest similarity first (reuses the same sort key as rank_similarities)
        qualifying.sort(key=lambda cr: -cr.best_face_similarity)
        result.selected = qualifying[0]

    # --- 5. Preserve metadata ---
    _write_selection_metadata(result, case_dir)

    return result


def _write_selection_metadata(result: SelectionResult, case_dir: Path) -> None:
    """Write a selection_metadata.json alongside the selected artifact."""
    meta = {
        "pipeline": "selected_candidate_integration",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "input_image": result.input_image,
        "threshold": result.threshold,
        "total_candidates": result.total_candidates,
        "evaluated": result.evaluated,
        "qualifying": result.qualifying,
        "message": result.message,
        "selected": result.selected.as_dict() if result.selected else None,
        "all_results": [cr.as_dict() for cr in result.all_results],
    }
    out = case_dir / "selection_metadata.json"
    out.write_text(json.dumps(meta, indent=2, default=str) + "\n", encoding="utf-8")
