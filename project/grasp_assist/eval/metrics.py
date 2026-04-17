from __future__ import annotations

import time


class MetricsTracker:
    def __init__(self):
        self.total_frames = 0
        self.detected_frames = 0
        self.guided_frames = 0
        self.ready_to_grasp_frames = 0
        self._latency_sum_ms = 0.0
        self._start = time.time()

    def update(self, latency_ms: float, hand_ok: bool, obj_ok: bool, message: str):
        self.total_frames += 1
        self._latency_sum_ms += latency_ms
        if hand_ok and obj_ok:
            self.detected_frames += 1
        if any(k in message for k in ["move", "good position", "向", "度", "近", "碰到"]):
            self.guided_frames += 1
        if any(k in message for k in ["碰到", "拿到", "good position"]):
            self.ready_to_grasp_frames += 1

    def summary(self) -> dict[str, float]:
        elapsed = max(time.time() - self._start, 1e-6)
        return {
            "frames": float(self.total_frames),
            "avg_latency_ms": self._latency_sum_ms / max(self.total_frames, 1),
            "joint_detection_rate": self.detected_frames / max(self.total_frames, 1),
            "guidance_rate": self.guided_frames / max(self.total_frames, 1),
            "ready_to_grasp_rate": self.ready_to_grasp_frames / max(self.total_frames, 1),
            "fps": self.total_frames / elapsed,
        }
