"""Downloads the official InsightFace model pack (SCRFD detector + ArcFace recogniser).

The models are the exact ONNX files published by the InsightFace project. We run
them with onnxruntime instead of the `insightface` pip package, because that
package must be compiled from source on Windows (Microsoft C++ Build Tools) and
its own model host is unreliable. Files land in the standard InsightFace cache
(~/.insightface/models/<pack>/) so an `insightface` install would reuse them.
"""
from pathlib import Path
import zipfile

import requests

MODEL_ROOT = Path.home() / ".insightface" / "models"

PACKS = {
    # 275 MB - SCRFD-10GF detector + ArcFace ResNet50 (glint360k). Best accuracy.
    "buffalo_l": {
        "url": "https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_l.zip",
        "detector": "det_10g.onnx",
        "recognizer": "w600k_r50.onnx",
    },
    # 16 MB - lighter/faster, slightly weaker. Useful on slow connections.
    "buffalo_s": {
        "url": "https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_s.zip",
        "detector": "det_500m.onnx",
        "recognizer": "w600k_mbf.onnx",
    },
}


def ensure_models(pack: str = "buffalo_l", quiet: bool = False) -> tuple[Path, Path]:
    """Return (detector_path, recognizer_path), downloading the pack if needed."""
    if pack not in PACKS:
        raise ValueError(f"unknown model pack {pack!r}; choose from {list(PACKS)}")
    spec = PACKS[pack]
    target = MODEL_ROOT / pack
    detector = target / spec["detector"]
    recognizer = target / spec["recognizer"]

    if detector.is_file() and recognizer.is_file():
        return detector, recognizer

    target.mkdir(parents=True, exist_ok=True)
    archive = target.with_suffix(".zip")
    if not archive.is_file():
        if not quiet:
            print(f"Downloading {pack} model pack from {spec['url']}")
        _download(spec["url"], archive, quiet=quiet)

    if not quiet:
        print(f"Extracting {archive.name} -> {target}")
    with zipfile.ZipFile(archive) as zf:
        zf.extractall(target)
    archive.unlink(missing_ok=True)

    # some builds of the zip nest everything one folder deeper
    if not detector.is_file():
        for found in target.rglob(spec["detector"]):
            found.replace(detector)
        for found in target.rglob(spec["recognizer"]):
            found.replace(recognizer)

    for path in (detector, recognizer):
        if not path.is_file():
            raise RuntimeError(f"model file missing after extraction: {path}")
    return detector, recognizer


def _download(url: str, dest: Path, quiet: bool = False) -> None:
    tmp = dest.with_suffix(dest.suffix + ".part")
    with requests.get(url, stream=True, timeout=60) as response:
        response.raise_for_status()
        total = int(response.headers.get("content-length", 0))
        done = 0
        with tmp.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=1024 * 512):
                handle.write(chunk)
                done += len(chunk)
                if not quiet and total:
                    print(f"\r  {done / 1e6:6.1f} / {total / 1e6:.1f} MB", end="")
    if not quiet:
        print()
    tmp.replace(dest)


if __name__ == "__main__":
    import sys

    name = sys.argv[1] if len(sys.argv) > 1 else "buffalo_l"
    det, rec = ensure_models(name)
    print(f"detector   : {det}")
    print(f"recognizer : {rec}")
