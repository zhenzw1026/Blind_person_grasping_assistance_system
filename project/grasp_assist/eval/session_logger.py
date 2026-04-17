from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path


class SessionLogger:
    def __init__(self, output_dir: str):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.session_dir = Path(output_dir) / f"session_{ts}"
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.frame_csv_path = self.session_dir / "frames.csv"
        self.summary_json_path = self.session_dir / "summary.json"

        self._f = self.frame_csv_path.open("w", newline="", encoding="utf-8")
        self._writer = csv.writer(self._f)
        self._writer.writerow(
            [
                "frame_id",
                "latency_ms",
                "hand_detected",
                "object_detected",
                "object_label",
                "object_conf",
                "message",
            ]
        )

    def log_frame(
        self,
        frame_id: int,
        latency_ms: float,
        hand_detected: bool,
        object_detected: bool,
        object_label: str | None,
        object_conf: float,
        message: str,
    ):
        self._writer.writerow(
            [
                frame_id,
                f"{latency_ms:.4f}",
                int(hand_detected),
                int(object_detected),
                object_label or "",
                f"{object_conf:.4f}",
                message,
            ]
        )

    def log_summary(self, summary: dict):
        with self.summary_json_path.open("w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)

    def close(self):
        self._f.close()
