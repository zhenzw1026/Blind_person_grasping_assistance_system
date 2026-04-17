from __future__ import annotations

import cv2
import numpy as np

from grasp_assist.config import ObjectConfig


def _normalize_label(label: str) -> str:
    text = (label or "").lower().strip()
    return "".join(ch for ch in text if ch.isalnum())


def _bbox_iou(box_a: tuple[int, int, int, int], box_b: tuple[int, int, int, int]) -> float:
    ax, ay, aw, ah = box_a
    bx, by, bw, bh = box_b
    ax2, ay2 = ax + aw, ay + ah
    bx2, by2 = bx + bw, by + bh

    inter_x1 = max(ax, bx)
    inter_y1 = max(ay, by)
    inter_x2 = min(ax2, bx2)
    inter_y2 = min(ay2, by2)
    if inter_x2 <= inter_x1 or inter_y2 <= inter_y1:
        return 0.0

    inter_area = float((inter_x2 - inter_x1) * (inter_y2 - inter_y1))
    area_a = float(max(1, aw * ah))
    area_b = float(max(1, bw * bh))
    return inter_area / max(area_a + area_b - inter_area, 1e-6)


class RedObjectDetector:
    def __init__(self, cfg: ObjectConfig):
        self.min_area = cfg.min_area

    def detect(self, frame_bgr):
        hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)

        lower1 = np.array([0, 120, 70])
        upper1 = np.array([10, 255, 255])
        lower2 = np.array([170, 120, 70])
        upper2 = np.array([180, 255, 255])

        mask1 = cv2.inRange(hsv, lower1, upper1)
        mask2 = cv2.inRange(hsv, lower2, upper2)
        mask = cv2.GaussianBlur(mask1 | mask2, (5, 5), 0)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return None, None, None, 0.0

        c = max(contours, key=cv2.contourArea)
        area = cv2.contourArea(c)
        if area < self.min_area:
            return None, None, None, 0.0

        x, y, w, h = cv2.boundingRect(c)
        center = (x + w // 2, y + h // 2)
        return center, (x, y, w, h), "red-object", 1.0


class YoloObjectDetector:
    def __init__(self, cfg: ObjectConfig):
        try:
            from ultralytics import YOLO
        except ImportError as exc:
            raise ImportError(
                "ultralytics is required for YOLO detector. Install with: pip install ultralytics"
            ) from exc

        self.model = YOLO(cfg.yolo_model)
        self.target_class = cfg.target_class.lower().strip() if cfg.target_class else None
        self.target_aliases = [self.target_class] if self.target_class else []
        self.conf_threshold = cfg.conf_threshold
        self.iou_threshold = cfg.iou_threshold
        self.imgsz = cfg.imgsz
        self.names = self.model.names

    def set_target_class(self, label: str | None, aliases: list[str] | None = None):
        self.target_class = label.lower().strip() if label else None
        normalized_aliases = []
        for item in aliases or []:
            if not item:
                continue
            normalized_aliases.append(item.lower().strip())
        if self.target_class and self.target_class not in normalized_aliases:
            normalized_aliases.insert(0, self.target_class)
        self.target_aliases = normalized_aliases

    def _matches_target(self, label: str) -> bool:
        if not self.target_class:
            return True

        norm_label = _normalize_label(label)
        candidates = self.target_aliases or [self.target_class]
        for cand in candidates:
            norm_cand = _normalize_label(cand)
            if norm_label == norm_cand or norm_label in norm_cand or norm_cand in norm_label:
                return True
        return False

    def detect(self, frame_bgr):
        predict_conf = max(0.05, self.conf_threshold * 0.7)
        results = self.model.predict(
            frame_bgr,
            verbose=False,
            conf=predict_conf,
            iou=self.iou_threshold,
            imgsz=self.imgsz,
        )
        if not results:
            return None, None, None, 0.0

        boxes = results[0].boxes
        if boxes is None or len(boxes) == 0:
            return None, None, None, 0.0

        best = None
        best_score = -1.0

        for box in boxes:
            cls_id = int(box.cls.item())
            conf = float(box.conf.item())
            label = str(self.names[cls_id]).lower()

            if conf < self.conf_threshold:
                continue
            if not self._matches_target(label):
                continue

            if conf > best_score:
                xyxy = box.xyxy[0].cpu().numpy().astype(int)
                x1, y1, x2, y2 = xyxy.tolist()
                w = max(1, x2 - x1)
                h = max(1, y2 - y1)
                best = (x1, y1, w, h, label, conf)
                best_score = conf

        if best is None:
            return None, None, None, 0.0

        x, y, w, h, label, conf = best
        center = (x + w // 2, y + h // 2)
        return center, (x, y, w, h), label, conf


class YoloWorldObjectDetector:
    def __init__(self, cfg: ObjectConfig):
        try:
            from ultralytics import YOLOWorld
        except ImportError as exc:
            raise ImportError(
                "ultralytics is required for YOLO-World detector. Install with: pip install ultralytics"
            ) from exc

        self.model = YOLOWorld(cfg.yolo_model)
        self.conf_threshold = cfg.conf_threshold
        self.iou_threshold = cfg.iou_threshold
        self.imgsz = max(320, int(cfg.imgsz))
        self.smooth_alpha = float(np.clip(cfg.temporal_smooth_alpha, 0.0, 0.95))
        self.max_lost_frames = max(0, int(cfg.max_lost_frames))
        self.prompts = [p.lower().strip() for p in (cfg.prompts or []) if p]
        self.target_class = cfg.target_class.lower().strip() if cfg.target_class else None
        self.target_candidates = [self.target_class] if self.target_class else []
        if not self.prompts and not self.target_class:
            self.prompts = ["object"]
        self._active_classes: list[str] | None = None
        self._last_box: tuple[int, int, int, int] | None = None
        self._last_label: str | None = None
        self._last_conf: float = 0.0
        self._lost_frames: int = 0

    def set_target_class(self, label: str | None, aliases: list[str] | None = None):
        self.target_class = label.lower().strip() if label else None
        candidates: list[str] = []
        if self.target_class:
            candidates.append(self.target_class)
        for item in aliases or []:
            if not item:
                continue
            normalized = item.lower().strip()
            if normalized and normalized not in candidates:
                candidates.append(normalized)
        self.target_candidates = candidates
        self._active_classes = None
        self._last_box = None
        self._last_label = None
        self._last_conf = 0.0
        self._lost_frames = 0

    def _ensure_classes(self):
        desired = self.target_candidates if self.target_candidates else self.prompts
        if not desired:
            desired = ["object"]
        if desired != self._active_classes:
            self.model.set_classes(desired)
            self._active_classes = list(desired)

    def _matches_target(self, label: str) -> bool:
        if not self.target_candidates:
            return True
        norm_label = _normalize_label(label)
        for cand in self.target_candidates:
            norm_cand = _normalize_label(cand)
            if norm_label == norm_cand or norm_label in norm_cand or norm_cand in norm_label:
                return True
        return False

    def _smooth_box(self, current_box: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
        if self._last_box is None:
            return current_box
        px, py, pw, ph = self._last_box
        x, y, w, h = current_box
        a = self.smooth_alpha
        sx = int(a * px + (1.0 - a) * x)
        sy = int(a * py + (1.0 - a) * y)
        sw = int(a * pw + (1.0 - a) * w)
        sh = int(a * ph + (1.0 - a) * h)
        return max(0, sx), max(0, sy), max(1, sw), max(1, sh)

    def _recover_recent_track(self):
        if self._last_box is None:
            return None, None, None, 0.0
        if self._lost_frames >= self.max_lost_frames:
            self._last_box = None
            self._last_label = None
            self._last_conf = 0.0
            return None, None, None, 0.0

        self._lost_frames += 1
        confidence = max(self._last_conf * (0.9 ** self._lost_frames), self.conf_threshold * 0.55)
        x, y, w, h = self._last_box
        center = (x + w // 2, y + h // 2)
        return center, self._last_box, self._last_label, confidence

    def detect(self, frame_bgr):
        self._ensure_classes()
        frame_h, frame_w = frame_bgr.shape[:2]
        frame_area = float(max(1, frame_w * frame_h))
        predict_conf = max(0.05, self.conf_threshold * 0.55)
        results = self.model.predict(
            frame_bgr,
            verbose=False,
            conf=predict_conf,
            iou=self.iou_threshold,
            imgsz=self.imgsz,
        )
        if not results:
            return self._recover_recent_track()

        boxes = results[0].boxes
        names = results[0].names if hasattr(results[0], "names") else self.model.names
        if boxes is None or len(boxes) == 0:
            return self._recover_recent_track()

        best = None
        best_score = -1.0

        for box in boxes:
            cls_id = int(box.cls.item())
            conf = float(box.conf.item())
            label = str(names[cls_id]).lower()

            if conf < self.conf_threshold * 0.65:
                continue

            if not self._matches_target(label):
                continue

            xyxy = box.xyxy[0].cpu().numpy().astype(int)
            x1, y1, x2, y2 = xyxy.tolist()
            w = max(1, x2 - x1)
            h = max(1, y2 - y1)
            candidate_box = (x1, y1, w, h)
            area_ratio = min(1.0, (w * h) / frame_area)
            iou_bonus = _bbox_iou(self._last_box, candidate_box) if self._last_box is not None else 0.0
            score = conf + 0.15 * iou_bonus + 0.1 * area_ratio
            if score > best_score:
                best = (x1, y1, w, h, label, conf)
                best_score = score

        if best is None:
            return self._recover_recent_track()

        x, y, w, h, label, conf = best
        smoothed_box = self._smooth_box((x, y, w, h))
        sx, sy, sw, sh = smoothed_box
        center = (sx + sw // 2, sy + sh // 2)

        self._last_box = smoothed_box
        self._last_label = label
        self._last_conf = conf
        self._lost_frames = 0
        return center, smoothed_box, label, conf


def build_object_detector(cfg: ObjectConfig):
    detector_name = cfg.detector.lower().strip()
    if detector_name == "red":
        return RedObjectDetector(cfg)
    if detector_name == "yolo":
        return YoloObjectDetector(cfg)
    if detector_name == "yolo_world":
        return YoloWorldObjectDetector(cfg)
    raise ValueError(f"Unsupported detector: {cfg.detector}. Expected 'red', 'yolo', or 'yolo_world'.")
