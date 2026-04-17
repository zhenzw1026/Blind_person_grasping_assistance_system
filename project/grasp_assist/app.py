from __future__ import annotations

import argparse

from grasp_assist.config import load_config
from grasp_assist.pipeline import GraspAssistPipeline


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Interactive vision-assisted grasping demo")
    p.add_argument("--config", type=str, default="configs/default.yaml", help="Path to YAML config")
    p.add_argument("--no-audio", action="store_true", help="Disable speech output")
    p.add_argument("--video", type=str, default=None, help="Video file path instead of webcam")
    p.add_argument("--no-display", action="store_true", help="Disable UI window display")
    return p


def main():
    args = build_parser().parse_args()
    cfg = load_config(args.config)
    pipeline = GraspAssistPipeline(cfg, enable_audio=not args.no_audio)
    source = args.video if args.video else None
    report = pipeline.run(source=source, display=not args.no_display)
    print("\n=== Session Summary ===")
    for k, v in report.items():
        if isinstance(v, float):
            print(f"{k}: {v:.4f}")
        else:
            print(f"{k}: {v}")


if __name__ == "__main__":
    main()
