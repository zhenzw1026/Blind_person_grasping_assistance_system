from __future__ import annotations

import base64
from threading import Lock
from pathlib import Path

import cv2
import numpy as np

from backend_api.models import BoundingBox, DetectionItem, GuideState, VisionFrameResponse, VoiceCommandResponse
from backend_api.session_manager import SessionContext
from grasp_assist.config import AppConfig, load_config
from grasp_assist.detectors.hand_tracker import HandTracker
from grasp_assist.detectors.object_detector import build_object_detector
from grasp_assist.guidance.policy import GuidancePolicy


class GraspAssistBridge:
    def __init__(self, config_path: str = "configs/default.yaml") -> None:
        cfg_path = Path(config_path)
        if not cfg_path.is_absolute():
            root_dir = Path(__file__).resolve().parents[1]
            cfg_path = root_dir / config_path
        cfg = load_config(str(cfg_path))
        self.cfg: AppConfig = cfg
        self.hand_tracker = HandTracker(cfg.hand)
        self.object_detector = build_object_detector(cfg.obj)
        self.policy = GuidancePolicy(cfg.guidance)
        self._lock = Lock()
        self._target_map = {
            "手机": ("cell phone", ["mobile phone", "phone", "smartphone"]),
            "杯子": ("cup", ["mug", "glass"]),
            "瓶子": ("bottle", ["water bottle"]),
            "键盘": ("keyboard", []),
            "鼠标": ("mouse", ["computer mouse"]),
            "眼镜": ("glasses", ["eyeglasses", "spectacles"]),
            "剪刀": ("scissors", []),
            "钥匙": ("key", ["keys"]),
            "书": ("book", []),
            "遥控器": ("remote", ["remote control"]),
            "苹果": ("apple", []),
            "手表": ("watch", ["wristwatch"]),
        }

    def apply_target(self, target_label: str) -> None:
        target = target_label.strip()
        en, aliases = self._target_map.get(target, (target.lower(), []))
        if hasattr(self.object_detector, "set_target_class"):
            self.object_detector.set_target_class(en, aliases=aliases)
        elif hasattr(self.object_detector, "target_class"):
            self.object_detector.target_class = en

    def process_frame(self, ctx: SessionContext, image_b64: str, mirror_x: bool) -> VisionFrameResponse:
        if ctx.done_latched:
            done_text = ctx.instruction or f"已拿到{ctx.target_label}，任务完成。"
            return VisionFrameResponse(
                state=GuideState.done,
                instruction=done_text,
                confidence=1.0,
                target_found=True,
                distance_hint="near",
                target_box=None,
                hand_box=None,
                detection_items=[],
                debug={"mirror_x": mirror_x, "latched_done": True},
            )

        frame = self._decode_image(image_b64)
        if mirror_x:
            frame = cv2.flip(frame, 1)

        with self._lock:
            hand_pt, hand_result = self.hand_tracker.detect_index_tip(frame)
            obj_pt, obj_box, obj_label, obj_conf = self.object_detector.detect(frame)

        h, w = frame.shape[:2]
        msg, grabbed = self.policy.generate(
            hand_pt,
            obj_pt,
            obj_box,
            obj_label,
            w,
            h,
            target_cn=ctx.target_label,
        )

        target_found = obj_box is not None
        hand_box = self._extract_hand_box(hand_result, frame.shape)
        target_box = None
        detections: list[DetectionItem] = []

        if obj_box is not None and obj_label is not None:
            x, y, bw, bh = obj_box
            target_box = BoundingBox(x=x, y=y, width=bw, height=bh)
            detections.append(
                DetectionItem(
                    label=obj_label,
                    confidence=float(obj_conf),
                    box=target_box,
                )
            )

        if hand_box is not None:
            detections.append(
                DetectionItem(
                    label="hand_index",
                    confidence=1.0,
                    box=hand_box,
                )
            )

        state = self._resolve_state(grabbed, target_found, hand_pt is not None, obj_box, obj_pt, hand_pt)
        if grabbed:
            state = GuideState.done
            ctx.done_latched = True
            msg = f"已拿到{ctx.target_label}，任务完成。"
        distance_hint = self._distance_hint(obj_box)

        ctx.state = state
        ctx.instruction = msg

        return VisionFrameResponse(
            state=state,
            instruction=msg,
            confidence=float(obj_conf),
            target_found=target_found,
            distance_hint=distance_hint,
            target_box=target_box,
            hand_box=hand_box,
            detection_items=detections,
            debug={
                "mirror_x": mirror_x,
                "has_target": target_found,
                "has_hand": hand_pt is not None,
                "target_label": obj_label,
            },
        )

    def process_voice(self, ctx: SessionContext, transcript: str) -> VoiceCommandResponse:
        text = (transcript or "").strip()
        normalized = "".join(ch for ch in text.lower() if not ch.isspace())

        if any(k in normalized for k in ["停止", "结束", "退出", "stop", "quit", "exit"]):
            ctx.state = GuideState.done
            ctx.done_latched = True
            ctx.instruction = "已停止引导"
            return VoiceCommandResponse(intent="stop", should_interrupt=True, feedback="已停止引导")

        if any(k in normalized for k in ["完成", "拿到了", "done", "complete"]):
            ctx.state = GuideState.done
            ctx.done_latched = True
            ctx.instruction = "任务完成"
            return VoiceCommandResponse(intent="complete", should_interrupt=False, feedback="任务完成")

        target = self._extract_target(text)
        if target:
            ctx.target_label = target
            ctx.done_latched = False
            self.apply_target(target)
            ctx.state = GuideState.searching
            ctx.instruction = f"收到，开始搜索{target}"
            return VoiceCommandResponse(
                intent="change_target",
                target_label=target,
                should_interrupt=False,
                feedback=f"收到，开始搜索{target}",
            )

        return VoiceCommandResponse(
            intent="chat",
            should_interrupt=False,
            feedback="已收到，请继续按提示操作",
        )

    def _extract_target(self, text: str) -> str | None:
        raw = (text or "").strip()
        if not raw:
            return None
        for key in self._target_map:
            if key in raw:
                return key
        prefixes = ["帮我找", "请帮我找", "我要找", "寻找", "找"]
        cleaned = raw
        for prefix in prefixes:
            cleaned = cleaned.replace(prefix, "")
        cleaned = cleaned.replace("。", "").replace("，", "").strip()
        if 1 <= len(cleaned) <= 10:
            return cleaned
        return None

    def _decode_image(self, image_b64: str) -> np.ndarray:
        payload = image_b64
        if "," in image_b64:
            payload = image_b64.split(",", 1)[1]
        try:
            binary = base64.b64decode(payload)
        except Exception as exc:
            raise ValueError("invalid image_b64") from exc

        image_array = np.frombuffer(binary, dtype=np.uint8)
        frame = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
        if frame is None:
            raise ValueError("cannot decode image")
        return frame

    def _resolve_state(
        self,
        grabbed: bool,
        target_found: bool,
        hand_found: bool,
        obj_box: tuple[int, int, int, int] | None,
        obj_pt: tuple[int, int] | None,
        hand_pt: tuple[int, int] | None,
    ) -> GuideState:
        if grabbed:
            return GuideState.done
        if not target_found:
            return GuideState.searching
        if not hand_found:
            return GuideState.target_locked

        if obj_box is not None:
            _, _, w, h = obj_box
            if w * h > self.cfg.guidance.far_area:
                return GuideState.near_field

        if obj_pt is not None and hand_pt is not None:
            dx = abs(obj_pt[0] - hand_pt[0])
            dy = abs(obj_pt[1] - hand_pt[1])
            if dx <= self.cfg.guidance.x_threshold and dy <= self.cfg.guidance.y_threshold:
                return GuideState.grasp_guide

        return GuideState.approaching

    def _distance_hint(self, obj_box: tuple[int, int, int, int] | None) -> str | None:
        if obj_box is None:
            return None
        _, _, w, h = obj_box
        area = w * h
        if area < self.cfg.guidance.near_area:
            return "far"
        if area > self.cfg.guidance.far_area:
            return "near"
        return "mid"

    @staticmethod
    def _extract_hand_box(hand_result, shape: tuple[int, int, int]) -> BoundingBox | None:
        if not hand_result or not hand_result.multi_hand_landmarks:
            return None

        frame_h, frame_w = shape[:2]
        points = hand_result.multi_hand_landmarks[0].landmark
        xs = [int(p.x * frame_w) for p in points]
        ys = [int(p.y * frame_h) for p in points]

        x1, x2 = max(0, min(xs)), min(frame_w - 1, max(xs))
        y1, y2 = max(0, min(ys)), min(frame_h - 1, max(ys))
        return BoundingBox(x=x1, y=y1, width=max(1, x2 - x1), height=max(1, y2 - y1))
