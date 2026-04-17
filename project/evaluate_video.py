from __future__ import annotations

import argparse
import json

from grasp_assist.config import load_config
from grasp_assist.pipeline import GraspAssistPipeline


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Offline evaluation on a recorded video")
    p.add_argument("--video", type=str, required=True, help="Input video path")
    p.add_argument("--config", type=str, default="configs/default.yaml", help="Config path")
    p.add_argument("--no-audio", action="store_true", help="Disable speech output")
    p.add_argument("--save", type=str, default="", help="Optional path to save summary JSON")
    return p


def main():
    args = build_parser().parse_args()
    cfg = load_config(args.config)
    cfg.runtime.display = False
    pipeline = GraspAssistPipeline(cfg, enable_audio=not args.no_audio)
    summary = pipeline.run(source=args.video, display=False)

    print("=== Offline Evaluation Summary ===")
    for k, v in summary.items():
        if isinstance(v, float):
            print(f"{k}: {v:.4f}")
        else:
            print(f"{k}: {v}")

    if args.save:
        with open(args.save, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)
        print(f"Saved summary to: {args.save}")


if __name__ == "__main__":
    main()
