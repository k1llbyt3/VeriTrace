"""SCRFD face detection (InsightFace det_10g / det_500m) run on onnxruntime.

"Face detection" = finding *where* faces are in an image. SCRFD returns a
bounding box, a confidence score, and five landmarks (both eyes, nose, both
mouth corners). ArcFace needs those landmarks to align the face crop.
"""
from dataclasses import dataclass

import cv2
import numpy as np
import onnxruntime


@dataclass
class Detection:
    """One detected face, in original-image pixel coordinates."""

    bbox: np.ndarray  # [x1, y1, x2, y2]
    score: float  # detector confidence, 0..1
    keypoints: np.ndarray  # shape (5, 2)

    @property
    def area(self) -> float:
        x1, y1, x2, y2 = self.bbox
        return float(max(0.0, x2 - x1) * max(0.0, y2 - y1))


def _nms(dets: np.ndarray, thresh: float) -> list[int]:
    """Greedy non-max suppression. `dets` = [x1,y1,x2,y2,score], score-sorted desc."""
    x1, y1, x2, y2 = dets[:, 0], dets[:, 1], dets[:, 2], dets[:, 3]
    areas = (x2 - x1 + 1) * (y2 - y1 + 1)
    order = np.arange(len(dets))
    keep: list[int] = []
    while order.size > 0:
        i = order[0]
        keep.append(int(i))
        rest = order[1:]
        inter_w = np.maximum(0.0, np.minimum(x2[i], x2[rest]) - np.maximum(x1[i], x1[rest]) + 1)
        inter_h = np.maximum(0.0, np.minimum(y2[i], y2[rest]) - np.maximum(y1[i], y1[rest]) + 1)
        inter = inter_w * inter_h
        iou = inter / (areas[i] + areas[rest] - inter)
        order = rest[iou <= thresh]
    return keep


class SCRFD:
    """Thin wrapper around an InsightFace SCRFD ONNX detector."""

    def __init__(self, model_path, det_size: int = 640, nms_thresh: float = 0.4):
        self.session = onnxruntime.InferenceSession(
            str(model_path), providers=["CPUExecutionProvider"]
        )
        self.input_name = self.session.get_inputs()[0].name
        self.output_names = [o.name for o in self.session.get_outputs()]

        n_out = len(self.output_names)
        if n_out in (6, 9):
            self.fmc, self.strides, self.num_anchors = 3, (8, 16, 32), 2
        elif n_out in (10, 15):
            self.fmc, self.strides, self.num_anchors = 5, (8, 16, 32, 64, 128), 1
        else:
            raise RuntimeError(f"unsupported SCRFD model with {n_out} outputs")
        self.use_kps = n_out in (9, 15)

        # SCRFD needs input dimensions divisible by 32
        det_size = max(160, int(det_size) // 32 * 32)
        self.det_size = (det_size, det_size)
        self.nms_thresh = nms_thresh
        self._center_cache: dict[tuple[int, int, int], np.ndarray] = {}

    def _anchor_centers(self, det_h: int, det_w: int, stride: int) -> np.ndarray:
        key = (det_h, det_w, stride)
        if key not in self._center_cache:
            rows, cols = det_h // stride, det_w // stride
            grid = np.stack(np.mgrid[:rows, :cols][::-1], axis=-1).astype(np.float32) * stride
            centers = grid.reshape(-1, 2)
            if self.num_anchors > 1:
                centers = np.stack([centers] * self.num_anchors, axis=1).reshape(-1, 2)
            self._center_cache[key] = centers
        return self._center_cache[key]

    def detect(self, image: np.ndarray, threshold: float = 0.5) -> list[Detection]:
        """Detect faces in a BGR uint8 image, strongest first."""
        det_h, det_w = self.det_size
        img_h, img_w = image.shape[:2]

        # letterbox into the model's square input without distorting aspect ratio
        if img_h / img_w > det_h / det_w:
            new_h, new_w = det_h, max(1, int(det_h * img_w / img_h))
        else:
            new_w, new_h = det_w, max(1, int(det_w * img_h / img_w))
        scale = new_h / img_h
        canvas = np.zeros((det_h, det_w, 3), dtype=np.uint8)
        canvas[:new_h, :new_w] = cv2.resize(image, (new_w, new_h))

        # BGR->RGB, normalise to roughly [-1, 1], NCHW
        blob = ((canvas[:, :, ::-1].astype(np.float32) - 127.5) / 128.0).transpose(2, 0, 1)[None]
        outputs = self.session.run(self.output_names, {self.input_name: blob})

        all_scores, all_boxes, all_kps = [], [], []
        for idx, stride in enumerate(self.strides):
            scores = outputs[idx].reshape(-1)
            keep = np.where(scores >= threshold)[0]
            if keep.size == 0:
                continue
            centers = self._anchor_centers(det_h, det_w, stride)
            deltas = outputs[idx + self.fmc].reshape(-1, 4) * stride
            boxes = np.stack(
                [
                    centers[:, 0] - deltas[:, 0],
                    centers[:, 1] - deltas[:, 1],
                    centers[:, 0] + deltas[:, 2],
                    centers[:, 1] + deltas[:, 3],
                ],
                axis=-1,
            )
            all_scores.append(scores[keep])
            all_boxes.append(boxes[keep])
            if self.use_kps:
                kps = outputs[idx + self.fmc * 2].reshape(-1, 5, 2) * stride
                all_kps.append((centers[:, None, :] + kps)[keep])

        if not all_scores:
            return []

        scores = np.concatenate(all_scores)
        boxes = np.concatenate(all_boxes) / scale
        order = scores.argsort()[::-1]
        dets = np.hstack([boxes, scores[:, None]]).astype(np.float32)[order]
        kpss = np.concatenate(all_kps)[order] / scale if self.use_kps else None

        results = []
        for i in _nms(dets, self.nms_thresh):
            results.append(
                Detection(
                    bbox=dets[i, :4],
                    score=float(dets[i, 4]),
                    keypoints=kpss[i] if kpss is not None else None,
                )
            )
        return results
