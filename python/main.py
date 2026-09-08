#!/usr/bin/env python
"""CLI entry point.

Usage:
    python python/main.py hash <file>        # SHA-256 of exact file bytes

More subcommands (face, compare, search, anchor, verify) are added as the
pipeline is built up milestone by milestone.
"""
import argparse
import json
import sys
from pathlib import Path

import config
from chain.registry import ChainError, fetch_by_hash, fetch_by_tx, register
from evidence.hashing import hash_report, hashes_match, sha256_file, to_bytes32
from search.lens import SearchError, search_google_lens
from search.downloader import DownloadError, preserve_case


def cmd_hash(args) -> int:
    try:
        report = hash_report(args.file)
    except (FileNotFoundError, IsADirectoryError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Algorithm : {report['algorithm']}")
    print(f"Artifact  : {report['file']}")
    print(f"Size      : {report['size_bytes']} bytes")
    print(f"Hash      : {report['sha256']}")
    print(f"Hashed at : {report['hashed_at']}")
    return 0


def cmd_face(args) -> int:
    """Detect faces in one image and report the ArcFace embedding."""
    from face.engine import InvalidImageError, get_engine

    try:
        engine = get_engine()
        faces = engine.analyse_file(args.image, threshold=args.det_threshold)
    except (InvalidImageError, FileNotFoundError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Image      : {args.image}")
    print(f"Model pack : {engine.pack}  (SCRFD detector + ArcFace embeddings)")
    print(f"Faces      : {len(faces)}")
    if not faces:
        print("\nERROR: no face detected - try a clearer/larger face or lower --det-threshold")
        return 2
    for face in faces:
        x1, y1, x2, y2 = (int(v) for v in face.bbox)
        marker = "  <- selected (largest face)" if face.index == 0 else ""
        print(
            f"  [{face.index}] box=({x1},{y1})-({x2},{y2})  "
            f"{x2 - x1}x{y2 - y1}px  confidence={face.det_score:.3f}{marker}"
        )
    selected = faces[0]
    preview = ", ".join(f"{v:+.4f}" for v in selected.embedding[:4])
    print(f"Embedding  : {selected.embedding.shape[0]} dimensions (unit length)")
    print(f"             first 4 values: [{preview}, ...]")
    return 0


def cmd_compare(args) -> int:
    """Cosine similarity between the main face of two local images."""
    from face.engine import InvalidImageError, NoFaceError, get_engine
    from face.similarity import cosine_similarity, passes_threshold

    try:
        engine = get_engine()
        face_a = engine.primary_embedding(args.image_a, threshold=args.det_threshold)
        face_b = engine.primary_embedding(args.image_b, threshold=args.det_threshold)
    except (InvalidImageError, NoFaceError, FileNotFoundError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    score = cosine_similarity(face_a.embedding, face_b.embedding)
    threshold = args.threshold if args.threshold is not None else config.FACE_SIMILARITY_THRESHOLD
    print(f"Image A    : {args.image_a}  (confidence {face_a.det_score:.3f})")
    print(f"Image B    : {args.image_b}  (confidence {face_b.det_score:.3f})")
    print(f"Similarity : {score:.4f}")
    print(f"Threshold  : {threshold:.2f}")
    verdict = "ABOVE threshold" if passes_threshold(score, threshold) else "BELOW threshold"
    print(f"Verdict    : {verdict}")
    print("Note       : higher cosine similarity means the embeddings are more alike;")
    print("             it is evidence of resemblance, not proof of identity.")
    return 0


def cmd_rank(args) -> int:
    """Rank local candidate images by their best detected-face similarity."""
    from face.engine import InvalidImageError, NoFaceError, get_engine
    from face.similarity import best_similarity, passes_threshold

    threshold = args.threshold if args.threshold is not None else config.FACE_SIMILARITY_THRESHOLD
    try:
        engine = get_engine()
        reference = engine.primary_embedding(args.reference, threshold=args.det_threshold)
        candidate_faces = [
            engine.analyse_file(path, threshold=args.det_threshold) for path in args.candidates
        ]
    except (InvalidImageError, NoFaceError, FileNotFoundError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    scores = []
    selected_faces = []
    for faces in candidate_faces:
        if not faces:
            scores.append(-1.0)
            selected_faces.append(None)
            continue
        score, face_index = best_similarity(
            reference.embedding, [face.embedding for face in faces]
        )
        scores.append(score)
        selected_faces.append(faces[face_index])

    ranked = sorted(
        range(len(scores)),
        key=lambda index: (-scores[index], index),
    )
    print(f"Reference  : {args.reference}  (confidence {reference.det_score:.3f})")
    print(f"Threshold  : {threshold:.2f}")
    print("Similarity : visual face similarity; decision is threshold qualification")
    for rank, index in enumerate(ranked, start=1):
        score = scores[index]
        decision = "QUALIFIES" if passes_threshold(score, threshold) else "does not qualify"
        face = selected_faces[index]
        confidence = f"confidence {face.det_score:.3f}" if face else "no face detected"
        print(
            f"{rank}. {args.candidates[index]}  similarity={score:.4f}  "
            f"{decision}  ({confidence})"
        )

    if not any(passes_threshold(score, threshold) for score in scores):
        print("NO VALID MATCH FOUND")
    return 0


def cmd_search(args) -> int:
    """Run Google Lens through SerpApi and print normalized candidates."""
    try:
        candidates = search_google_lens(args.image_url, search_type=args.type, limit=args.limit)
    except SearchError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Image URL : {args.image_url}")
    print(f"Results   : {len(candidates)}")
    for candidate in candidates:
        print(f"[{candidate.search_type} #{candidate.search_rank}] {candidate.title or '(untitled)'}")
        print(f"  Source  : {candidate.domain}")
        print(f"  URL     : {candidate.source_url or '(none)'}")
        print(f"  Image   : {candidate.image_url or '(none)'}")
    return 0


def cmd_preserve(args) -> int:
    """Search Lens and preserve the input plus the first accessible candidate."""
    try:
        candidates = search_google_lens(args.image_url, search_type=args.type, limit=args.limit)
        if not candidates:
            raise DownloadError("Google Lens returned no candidates")
        metadata = preserve_case(args.image_url, candidates, config.ARTIFACTS_DIR / args.case)
    except (SearchError, DownloadError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    candidate = metadata["candidate"]
    print(f"Candidate found: {candidate['title'] or '(untitled)'}")
    print(f"Downloaded: {candidate['image_url']}")
    print(f"Size: {candidate['size_bytes']} bytes")
    print(f"Saved: {config.ARTIFACTS_DIR / args.case / candidate['local_artifact_filename']}")
    print(f"Metadata: {config.ARTIFACTS_DIR / args.case / 'metadata.json'}")
    return 0


def cmd_select(args) -> int:
    """End-to-end candidate selection: Lens → download → face compare → rank → select."""
    from pipeline import select_candidate

    threshold = args.threshold if args.threshold is not None else config.FACE_SIMILARITY_THRESHOLD
    try:
        result = select_candidate(
            input_image=args.input_image,
            case_id=args.case,
            threshold=threshold,
            search_type=args.type,
            limit=args.limit,
            source_url=args.source_url,
        )
    except (SearchError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"Input image : {result.input_image}")
    print(f"Threshold   : {result.threshold:.2f}")
    print(f"Candidates  : {result.total_candidates} found, {result.evaluated} downloaded, "
          f"{result.qualifying} qualifying")
    print()

    if not result.total_candidates:
        print("NO PUBLIC MATCHES FOUND")
        print("Google Lens returned no public matches for this image.")
        return 0

    # Show all evaluated candidates ranked by similarity
    ranked = sorted(result.all_results, key=lambda cr: -cr.best_face_similarity)
    for rank, cr in enumerate(ranked, start=1):
        status = "QUALIFIES" if cr.qualifies else "does not qualify"
        if cr.error and not cr.downloaded:
            status = f"SKIPPED ({cr.error})"
        elif cr.error:
            status = f"ERROR ({cr.error})"
        print(f"  {rank}. [{cr.candidate.candidate_id}] "
              f"similarity={cr.best_face_similarity:.4f}  {status}")
        print(f"     {cr.candidate.title or '(untitled)'} — {cr.candidate.domain}")

    print()
    if result.has_selection:
        sel = result.selected
        print("=" * 40)
        print("SELECTED CANDIDATE")
        print("=" * 40)
        print(f"  ID         : {sel.candidate.candidate_id}")
        print(f"  Title      : {sel.candidate.title or '(untitled)'}")
        print(f"  Source URL : {sel.candidate.source_url}")
        print(f"  Image URL  : {sel.candidate.image_url}")
        print(f"  Similarity : {sel.best_face_similarity:.4f}")
        print(f"  Artifact   : {sel.local_path}")
        print(f"  Size       : {sel.size_bytes} bytes")
        print(f"  Metadata   : {result.case_dir / 'selection_metadata.json'}")
    else:
        print("=" * 40)
        print("NO CANDIDATE PASSES THRESHOLD")
        print("=" * 40)
        print(f"None of the {result.total_candidates} candidates achieved "
              f"similarity >= {result.threshold:.2f}")
    return 0


def cmd_anchor(args) -> int:
    """SHA-256 a local file and record that fingerprint on the blockchain."""
    case_dir = None
    source_url = args.url or ""
    artifact = args.file
    if args.case:
        try:
            case_dir, selected = _selected_case_artifact(args.case)
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        if artifact is None:
            artifact = selected["local_path"]
        if not source_url:
            source_url = selected.get("source_url") or ""
    if artifact is None:
        print("ERROR: provide a file, or use --case for a selected candidate", file=sys.stderr)
        return 1
    try:
        report = hash_report(artifact)
    except (FileNotFoundError, IsADirectoryError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Artifact   : {report['file']}")
    print(f"Size       : {report['size_bytes']} bytes")
    print(f"SHA-256    : {report['sha256']}")
    print("Submitting transaction to the blockchain...")
    try:
        result = register(report["bytes32"], source_url)
    except ChainError as exc:
        print(f"\nBLOCKCHAIN ERROR: {exc}", file=sys.stderr)
        return 4
    _write_anchoring_metadata(case_dir, report, source_url, result)
    if result.get("alreadyRegistered"):
        print("\nThis fingerprint was already on-chain - no second transaction was sent.")
        print(f"Registered at : {result['registeredAt']} (unix time)")
        print(f"Source URL    : {result['sourceUrl']}")
        if case_dir:
            print(f"Evidence      : {case_dir / 'anchoring_metadata.json'}")
        return 0
    print(f"Chain id   : {result['chainId']}")
    print(f"Contract   : {result['contractAddress']}")
    print(f"Tx hash    : {result['txHash']}")
    print(f"Block      : {result['blockNumber']}  (gas used {result['gasUsed']})")
    print(f"Status     : {result['status']}")
    if case_dir:
        print(f"Evidence   : {case_dir / 'anchoring_metadata.json'}")
    print(f"\nKeep this transaction hash - it is how you verify later:\n  {result['txHash']}")
    return 0


def cmd_verify(args) -> int:
    """Re-hash an artifact and compare it against the fingerprint stored on-chain."""
    artifact = args.artifact
    recorded_hash = None
    if args.case:
        try:
            case_dir = _case_dir(args.case)
            anchoring = json.loads((case_dir / "anchoring_metadata.json").read_text(encoding="utf-8"))
            artifact = artifact or anchoring["artifact"]["file"]
            recorded_hash = anchoring["registered_hash"]
            args.tx = args.tx or anchoring.get("transaction_hash")
        except (OSError, KeyError, ValueError, json.JSONDecodeError) as exc:
            print(f"ERROR: cannot load anchoring metadata for {args.case}: {exc}", file=sys.stderr)
            return 1
    if artifact is None:
        print("ERROR: provide --artifact, or use --case with anchoring metadata", file=sys.stderr)
        return 1
    try:
        computed = sha256_file(artifact)
    except (FileNotFoundError, IsADirectoryError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    try:
        if args.tx:
            record = fetch_by_tx(args.tx)
        else:
            # Case verification must retrieve the original registered hash, not
            # the newly computed one; otherwise a changed artifact could not
            # produce a meaningful FAILED verdict.
            record = fetch_by_hash(to_bytes32(recorded_hash or computed))
    except ChainError as exc:
        print(f"Computed hash   : {computed}")
        print(f"\nBLOCKCHAIN LOOKUP FAILED: {exc}", file=sys.stderr)
        print("(no on-chain record to compare against - cannot verify)")
        return 4
    on_chain = record["onChainHash"].removeprefix("0x").lower()
    print(f"Artifact        : {artifact}")
    print(f"Algorithm       : SHA-256")
    print(f"Retrieved from  : {record['source']} (chain id {record['chainId']})")
    print(f"Source URL      : {record.get('sourceUrl') or '(none recorded)'}")
    print(f"Registrant      : {record.get('registrant')}")
    print()
    print(f"Blockchain hash : {on_chain}")
    print(f"Computed hash   : {computed}")
    print()
    if hashes_match(on_chain, computed):
        print("=" * 34)
        print("BLOCKCHAIN VERIFICATION PASSED")
        print("=" * 34)
        print("The artifact is byte-for-byte identical to the registered fingerprint.")
        return 0
    print("=" * 34)
    print("VERIFICATION FAILED")
    print("=" * 34)
    print("The artifact's bytes differ from the fingerprint recorded on-chain.")
    return 3


def _case_dir(case_id: str) -> Path:
    """Return a direct child of artifacts/, rejecting traversal-like case IDs."""
    candidate = Path(case_id)
    if not case_id or candidate.name != case_id or case_id in {".", ".."}:
        raise ValueError("case must be a single directory name under artifacts/")
    return config.ARTIFACTS_DIR / candidate


def _selected_case_artifact(case_id: str) -> tuple[Path, dict]:
    """Load the artifact selected by the existing candidate-selection pipeline."""
    case_dir = _case_dir(case_id)
    try:
        selection = json.loads((case_dir / "selection_metadata.json").read_text(encoding="utf-8"))
        selected = selection["selected"]
    except (OSError, KeyError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot load selected candidate metadata for {case_id}: {exc}") from exc
    if not selected or not selected.get("qualifies") or not selected.get("local_path"):
        raise ValueError(f"case {case_id} has no qualifying selected candidate to anchor")
    return case_dir, selected


def _write_anchoring_metadata(case_dir: Path | None, report: dict, source_url: str, result: dict) -> None:
    """Preserve the on-chain receipt beside selected case evidence when available."""
    if case_dir is None:
        return
    registered_hash = result.get("onChainHash") or result.get("contentHash") or report["bytes32"]
    previous = {}
    metadata_path = case_dir / "anchoring_metadata.json"
    if result.get("alreadyRegistered") and metadata_path.is_file():
        try:
            previous = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            previous = {}
    metadata = {
        "artifact": report,
        "registered_hash": registered_hash,
        "source_url": result.get("sourceUrl", source_url),
        "transaction_hash": result.get("txHash") or previous.get("transaction_hash"),
        "block_number": result.get("blockNumber") or previous.get("block_number"),
        "chain_id": result.get("chainId"),
        "contract_address": result.get("contractAddress"),
        "registration_status": result.get("status", "already_registered"),
        "already_registered": bool(result.get("alreadyRegistered")),
    }
    metadata_path.write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="Face identification + blockchain verification pipeline",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_hash = sub.add_parser("hash", help="SHA-256 fingerprint of a file")
    p_hash.add_argument("file", help="path to the file to fingerprint")
    p_hash.set_defaults(func=cmd_hash)

    p_face = sub.add_parser("face", help="detect faces + build an ArcFace embedding")
    p_face.add_argument("image", help="path to an image containing a face")
    p_face.add_argument("--det-threshold", type=float, default=0.5, help="detector confidence cutoff")
    p_face.set_defaults(func=cmd_face)

    p_cmp = sub.add_parser("compare", help="cosine similarity between two local face images")
    p_cmp.add_argument("image_a")
    p_cmp.add_argument("image_b")
    p_cmp.add_argument("--threshold", type=float, default=None, help="override FACE_SIMILARITY_THRESHOLD")
    p_cmp.add_argument("--det-threshold", type=float, default=0.5)
    p_cmp.set_defaults(func=cmd_compare)

    p_rank = sub.add_parser("rank", help="rank local candidate face images by similarity")
    p_rank.add_argument("reference", help="path to the reference face image")
    p_rank.add_argument("candidates", nargs="+", help="candidate image paths")
    p_rank.add_argument("--threshold", type=float, default=None, help="override FACE_SIMILARITY_THRESHOLD")
    p_rank.add_argument("--det-threshold", type=float, default=0.5)
    p_rank.set_defaults(func=cmd_rank)

    p_search = sub.add_parser("search", help="Google Lens reverse-image search via SerpApi")
    p_search.add_argument("--image-url", required=True, help="publicly accessible image URL")
    p_search.add_argument("--type", choices=("all", "exact_matches", "visual_matches"), default="all")
    p_search.add_argument("--limit", type=int, default=20)
    p_search.set_defaults(func=cmd_search)

    p_preserve = sub.add_parser("preserve", help="download and preserve a Lens candidate")
    p_preserve.add_argument("--image-url", required=True, help="publicly accessible input image URL")
    p_preserve.add_argument("--case", default="case-001")
    p_preserve.add_argument("--type", choices=("all", "exact_matches", "visual_matches"), default="visual_matches")
    p_preserve.add_argument("--limit", type=int, default=20)
    p_preserve.set_defaults(func=cmd_preserve)

    p_select = sub.add_parser("select-candidate", help="end-to-end: Lens → download → face compare → select best candidate")
    p_select.add_argument("input_image", help="path to local reference face image")
    p_select.add_argument("--case", default="case-001", help="case directory name")
    p_select.add_argument("--threshold", type=float, default=None, help="override FACE_SIMILARITY_THRESHOLD")
    p_select.add_argument("--type", choices=("all", "exact_matches", "visual_matches"), default="visual_matches")
    p_select.add_argument("--limit", type=int, default=20)
    p_select.add_argument(
        "--source-url",
        help="public source page or image URL used for Google Lens (optional)",
    )
    p_select.set_defaults(func=cmd_select)

    p_anchor = sub.add_parser("anchor", help="SHA-256 a file and record it on the blockchain")
    p_anchor.add_argument("file", nargs="?", help="artifact to anchor (optional with --case)")
    p_anchor.add_argument("--case", help="anchor the qualifying selected candidate for this case")
    p_anchor.add_argument("--url", default="", help="source URL to store alongside the hash")
    p_anchor.set_defaults(func=cmd_anchor)

    p_verify = sub.add_parser("verify", help="re-hash an artifact and compare with the chain")
    p_verify.add_argument("--artifact", help="the exact file to verify (optional with --case)")
    p_verify.add_argument("--case", help="use saved anchoring metadata for this case")
    p_verify.add_argument("--tx", default=None, help="registration transaction hash (recommended)")
    p_verify.set_defaults(func=cmd_verify)

    return parser


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
