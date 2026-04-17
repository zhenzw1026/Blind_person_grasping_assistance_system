from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class CameraConfig:
    index: int = 0
    width: int = 960
    height: int = 540


@dataclass
class HandConfig:
    max_num_hands: int = 1
    min_detection_confidence: float = 0.5
    min_tracking_confidence: float = 0.5


@dataclass
class ObjectConfig:
    detector: str = "yolo_world"
    min_area: int = 700
    yolo_model: str = "yolov8n.pt"
    target_class: str = "bottle"
    conf_threshold: float = 0.35
    iou_threshold: float = 0.6
    imgsz: int = 640
    detect_interval_frames: int = 2
    temporal_smooth_alpha: float = 0.65
    max_lost_frames: int = 4
    prompts: list[str] = field(default_factory=lambda: [
        "cup",
        "bottle",
        "cell phone",
        "scissors",
    ])


@dataclass
class GuidanceConfig:
    x_threshold: int = 35
    y_threshold: int = 35
    near_area: int = 10000
    far_area: int = 26000


@dataclass
class AudioConfig:
    enabled: bool = True
    speech_interval_sec: float = 0.9
    rate: int = 150
    tts_backend: str = "pyttsx3"
    tts_log_events: bool = True
    reaction_grace_sec: float = 1.4
    min_guidance_interval_sec: float = 2.0
    guidance_repeat_sec: float = 5.0
    recognizer: str = "whisper"
    whisper_model: str = "base"
    language: str = "zh"
    listen_timeout: float = 15.0
    phrase_time_limit: float = 8.0
    ambient_adjust_sec: float = 1.2
    dynamic_energy_threshold: bool = True
    energy_threshold: int = 300
    pause_threshold: float = 0.8
    non_speaking_duration: float = 0.4
    command_cooldown_sec: float = 0.6
    fallback_google: bool = True
    google_language: str = "zh-CN"
    whisper_beam_size: int = 5
    whisper_best_of: int = 5
    whisper_temperature: float = 0.0
    whisper_initial_prompt: str = "普通话语音指令，场景是寻物。常见命令：帮我找手机，帮我找杯子，找钥匙，找鼠标。"


@dataclass
class RuntimeConfig:
    draw_debug: bool = True
    window_name: str = "Grasp Assist Demo"
    display: bool = True
    record_session: bool = True
    output_dir: str = "outputs"
    ui_enable_unicode: bool = True
    ui_font_path: str = ""
    ui_font_size: int = 26


@dataclass
class AppConfig:
    camera: CameraConfig = field(default_factory=CameraConfig)
    hand: HandConfig = field(default_factory=HandConfig)
    obj: ObjectConfig = field(default_factory=ObjectConfig)
    guidance: GuidanceConfig = field(default_factory=GuidanceConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    runtime: RuntimeConfig = field(default_factory=RuntimeConfig)


def _update_dataclass(dc: Any, values: dict[str, Any]) -> Any:
    for k, v in values.items():
        if not hasattr(dc, k):
            continue
        current = getattr(dc, k)
        if hasattr(current, "__dataclass_fields__") and isinstance(v, dict):
            _update_dataclass(current, v)
        else:
            setattr(dc, k, v)
    return dc


def load_config(config_path: str | None = None) -> AppConfig:
    cfg = AppConfig()
    if not config_path:
        return cfg

    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {config_path}")

    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    _update_dataclass(cfg, raw)
    return cfg
