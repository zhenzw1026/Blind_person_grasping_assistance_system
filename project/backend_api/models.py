from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class GuideState(str, Enum):
    searching = "searching"
    target_locked = "target_locked"
    approaching = "approaching"
    near_field = "near_field"
    grasp_guide = "grasp_guide"
    done = "done"


class BoundingBox(BaseModel):
    x: int
    y: int
    width: int
    height: int


class DetectionItem(BaseModel):
    label: str
    confidence: float
    box: BoundingBox


class SessionStartRequest(BaseModel):
    target_label: str = Field(min_length=1, max_length=64)


class SessionResponse(BaseModel):
    session_id: str
    target_label: str
    state: GuideState
    current_instruction: str


class SessionSettingsRequest(BaseModel):
    speech_rate: str = Field(default="medium")
    offline_mode: bool = False


class VisionFrameRequest(BaseModel):
    session_id: str
    frame_width: int = Field(ge=1)
    frame_height: int = Field(ge=1)
    mirror_x: bool = True
    image_b64: str
    server_detect: bool = True
    detect_conf: float = 0.15
    detections: list[dict[str, Any]] = Field(default_factory=list)


class VisionFrameResponse(BaseModel):
    state: GuideState
    instruction: str
    confidence: float
    target_found: bool
    distance_hint: str | None
    target_box: BoundingBox | None
    hand_box: BoundingBox | None
    detection_items: list[DetectionItem] = Field(default_factory=list)
    debug: dict[str, Any] | None = None


class VoiceCommandRequest(BaseModel):
    session_id: str
    transcript: str = Field(min_length=1)
    offline_mode: bool = False


class VoiceCommandResponse(BaseModel):
    intent: str
    target_label: str | None = None
    should_interrupt: bool
    feedback: str
