"""ArcFace face embeddings (InsightFace w600k_r50 / w600k_mbf) on onnxruntime.

An "embedding" is a fixed-length list of numbers (512 here) that summarises a
face. Two photos of the same person give embeddings pointing in a similar
direction - which is exactly what cosine similarity measures. Before embedding,
the face is warped onto a standard 112x112 template using the five landmarks
from SCRFD, so pose and scale differences do not dominate the result.
"""
import cv2
import numpy as np
import onnxruntime

# Canonical landmark positions ArcFace was trained on (112x112 crop).
ARCFACE_TEMPLATE = np.array(
    [
        [38.2946, 51.6963],  # left eye
        [73.5318, 51.5014],  # right eye
        [56.0252, 71.7366],  # nose tip
        [41.5493, 92.3655],  # left mouth corner
        [70.7299, 92.2041],  # right mouth corner
    ],
    dtype=np.float64,
)


def _similarity_transform(src: np.ndarray, dst: np.ndarray) -> np.ndarray:
    """Least-squares 2x3 similarity matrix (rotate + uniform scale + translate)."""
    src = np.asarray(src, dtype=np.float64)
    dst = np.asarray(dst, dtype=np.float64)
    src_centred = src - src.mean(axis=0)
    dst_centred = dst - dst.mean(axis=0)
    norm = float((src_centred**2).sum())
    if norm == 0:
        raise ValueError("degenerate landmarks: all points identical")
    a = float((src_centred * dst_centred).sum() / norm)  # scale * cos(angle)
    b = float((src_centred[:, 0] * dst_centred[:, 1] - src_centred[:, 1] * dst_centred[:, 0]).sum() / norm)
    rotation = np.array([[a, -b], [b, a]])
    translation = dst.mean(axis=0) - rotation @ src.mean(axis=0)
    return np.hstack([rotation, translation[:, None]]).astype(np.float32)


def align_face(image: np.ndarray, keypoints: np.ndarray, size: int = 112) -> np.ndarray:
    """Warp a face onto the standard ArcFace template using its 5 landmarks."""
    if keypoints is None or len(keypoints) != 5:
        raise ValueError("ArcFace alignment needs exactly 5 landmarks")
    template = ARCFACE_TEMPLATE * (size / 112.0)
    matrix = _similarity_transform(np.asarray(keypoints, dtype=np.float64), template)
    return cv2.warpAffine(image, matrix, (size, size), borderValue=0.0)


class ArcFace:
    """Thin wrapper around an InsightFace ArcFace ONNX recognition model."""

    def __init__(self, model_path):
        self.session = onnxruntime.InferenceSession(
            str(model_path), providers=["CPUExecutionProvider"]
        )
        model_input = self.session.get_inputs()[0]
        self.input_name = model_input.name
        self.output_names = [o.name for o in self.session.get_outputs()]
        shape = model_input.shape  # [1, 3, H, W]
        self.input_size = int(shape[2]) if isinstance(shape[2], int) else 112
        self.dim = int(self.session.get_outputs()[0].shape[-1])

    def embed(self, image: np.ndarray, keypoints: np.ndarray) -> np.ndarray:
        """Return a unit-length embedding for one face in a BGR image."""
        crop = align_face(image, keypoints, self.input_size)
        blob = ((crop[:, :, ::-1].astype(np.float32) - 127.5) / 127.5).transpose(2, 0, 1)[None]
        vector = self.session.run(self.output_names, {self.input_name: blob})[0].reshape(-1)
        norm = float(np.linalg.norm(vector))
        if norm == 0:
            raise RuntimeError("ArcFace produced an all-zero embedding")
        return (vector / norm).astype(np.float32)
