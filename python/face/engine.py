"""Face pipeline facade: image -> SCRFD detection -> ArcFace embedding.

Loading the ONNX models takes a couple of seconds, so one engine instance is
reused for the input image and every downloaded candidate.
"""
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

import config
from face.detector import SCRFD, Detection
from face.embedding import ArcFace
from face.models import ensure_models


class NoFaceError(ValueError):
    """Raised when an image contains no detectable face."""


class InvalidImageError(ValueError):
    """Raised when a file cannot be decoded as an image."""


@dataclass
class FaceRecord:
    """One detected + embedded face."""

    index: int
    bbox: list[float]
    det_score: float
    embedding: np.ndarray = field(repr=False)

    @property
    def area(self) -> float:
        x1, y1, x2, y2 = self.bbox
        return max(0.0, x2 - x1) * max(0.0, y2 - y1)


def load_image(path) -> np.ndarray:
    """Read an image file into a BGR uint8 array. Raises InvalidImageError."""
    path = Path(path)
    if not path.is_file():
        raise InvalidImageError(f"file not found: {path}")
    # np.fromfile + imdecode so non-ASCII Windows paths work
    try:
        buffer = np.frombuffer(path.read_bytes(), dtype=np.uint8)
        image = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
    except Exception:  # noqa: BLE001 - any decode problem is the same failure here
        image = None
    if image is None:  # last resort: Pillow handles a few formats OpenCV refuses
        try:
            from PIL import Image

            with Image.open(path) as pil_image:
                image = cv2.cvtColor(np.array(pil_image.convert("RGB")), cv2.COLOR_RGB2BGR)
        except Exception as exc:  # noqa: BLE001
            raise InvalidImageError(f"cannot decode image: {path} ({exc})") from exc
    if image.size == 0:
        raise InvalidImageError(f"empty image: {path}")
    return image


class FaceEngine:
    """SCRFD + ArcFace, loaded once."""

    def __init__(self, pack: str | None = None, det_size: int | None = None):
        self.pack = pack or config.INSIGHTFACE_MODEL
        detector_path, recognizer_path = ensure_models(self.pack, quiet=True)
        self.detector = SCRFD(detector_path, det_size=det_size or config.DET_SIZE)
        self.recognizer = ArcFace(recognizer_path)

    @property
    def dim(self) -> int:
        return self.recognizer.dim

    def analyse_image(self, image: np.ndarray, threshold: float = 0.5) -> list[FaceRecord]:
        """Detect every face and embed it. Largest face first."""
        detections: list[Detection] = self.detector.detect(image, threshold=threshold)
        records = []
        for detection in detections:
            if detection.keypoints is None:
                continue
            records.append(
                FaceRecord(
                    index=0,
                    bbox=[float(v) for v in detection.bbox],
                    det_score=detection.score,
                    embedding=self.recognizer.embed(image, detection.keypoints),
                )
            )
        # documented selection rule: the largest face is the intended subject
        records.sort(key=lambda record: record.area, reverse=True)
        for position, record in enumerate(records):
            record.index = position
        return records

    def analyse_file(self, path, threshold: float = 0.5) -> list[FaceRecord]:
        return self.analyse_image(load_image(path), threshold=threshold)

    def primary_embedding(self, path, threshold: float = 0.5) -> FaceRecord:
        """The face we treat as the subject: the largest detected face."""
        faces = self.analyse_file(path, threshold=threshold)
        if not faces:
            raise NoFaceError(f"no face detected in {path}")
        return faces[0]


_engine: FaceEngine | None = None


def get_engine() -> FaceEngine:
    """Process-wide singleton so the ONNX models load only once."""
    global _engine
    if _engine is None:
        _engine = FaceEngine()
    return _engine
