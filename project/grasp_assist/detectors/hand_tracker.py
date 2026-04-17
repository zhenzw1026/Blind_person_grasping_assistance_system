from __future__ import annotations

import cv2
import mediapipe as mp

from grasp_assist.config import HandConfig


class HandTracker:
    def __init__(self, cfg: HandConfig):
        self.mp_hands = mp.solutions.hands
        self.mp_draw = mp.solutions.drawing_utils
        self.hands = self.mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=cfg.max_num_hands,
            min_detection_confidence=cfg.min_detection_confidence,
            min_tracking_confidence=cfg.min_tracking_confidence,
        )

    def detect_index_tip(self, frame_bgr):
        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        result = self.hands.process(frame_rgb)
        if not result.multi_hand_landmarks:
            return None, result

        hand = result.multi_hand_landmarks[0]
        h, w, _ = frame_bgr.shape
        tip = hand.landmark[8]
        return (int(tip.x * w), int(tip.y * h)), result

    def close(self):
        self.hands.close()
