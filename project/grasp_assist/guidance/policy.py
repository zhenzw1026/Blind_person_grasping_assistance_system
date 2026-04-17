from __future__ import annotations

import math

from grasp_assist.config import GuidanceConfig

class GuidancePolicy:
    def __init__(self, cfg: GuidanceConfig):
        self.cfg = cfg
        self.label_map = {
            "cup": "杯子",
            "bottle": "瓶子",
            "cell phone": "手机",
            "mobile phone": "手机",
            "phone": "手机",
            "smartphone": "手机",
            "apple": "苹果",
            "mouse": "鼠标",
            "keyboard": "键盘",
            "book": "书",
            "remote": "遥控器",
            "key": "钥匙",
            "red-object": "红色目标"
        }

    def generate(self, hand_pt, obj_pt, obj_box, obj_label, frame_w, frame_h, target_cn: str | None = None) -> tuple[str, bool]:
        cn_label = target_cn or (self.label_map.get(str(obj_label).lower(), str(obj_label)) if obj_label else "目标")

        # Confirm grasp before early-returning on missing center point.
        # In real scenes, center points can jitter/drop for a few frames when the hand occludes the target.
        if hand_pt is not None and obj_box is not None:
            hx, hy = hand_pt
            x, y, w, h = obj_box
            px, py = max(22, int(w * 0.25)), max(22, int(h * 0.25))
            cx, cy = x + w / 2.0, y + h / 2.0
            dist = math.hypot(hx - cx, hy - cy)
            in_box = (x - px <= hx <= x + w + px) and (y - py <= hy <= y + h + py)
            close_center = dist <= max(20.0, min(w, h) * 0.45)
            if in_box or close_center:
                return f"您已经拿到{cn_label}。", True

        if obj_pt is None and obj_box is None:
            return f"未检测到{cn_label}。请左右慢慢转身，向前半步继续找。", False

        if obj_pt is not None:
            ox, oy = obj_pt
        else:
            x, y, w, h = obj_box
            ox, oy = x + w // 2, y + h // 2
        center_x = frame_w / 2
        dx_from_center = ox - center_x
        angle = int(math.degrees(math.atan2(abs(dx_from_center), max(frame_h - oy, 1.0))))

        if abs(dx_from_center) <= self.cfg.x_threshold:
            direction_text = "正前方"
        elif dx_from_center < 0:
            direction_text = f"左前方约{angle}度"
        else:
            direction_text = f"右前方约{angle}度"

        distance_text = ""
        if obj_box is not None:
            _, _, w, h = obj_box
            area = w * h
            if area < self.cfg.near_area:
                distance_text = "目标偏远，请向前走一小步。"
            elif area > self.cfg.far_area:
                distance_text = "目标已经很近，请放慢动作。"
            else:
                distance_text = "目标距离合适。"

        head = f"{cn_label}在{direction_text}。{distance_text}".strip()

        if hand_pt is None:
            return f"{head} 请先把手伸到镜头前。", False

        hx, hy = hand_pt
        hdx = ox - hx
        hdy = oy - hy

        if hdx > self.cfg.x_threshold:
            x_move = "手向右移动"
        elif hdx < -self.cfg.x_threshold:
            x_move = "手向左移动"
        else:
            x_move = "手左右方向基本正确"

        if hdy > self.cfg.y_threshold:
            y_move = "手向下移动"
        elif hdy < -self.cfg.y_threshold:
            y_move = "手向上移动"
        else:
            y_move = "手上下方向基本正确"

        if abs(hdx) <= self.cfg.x_threshold and abs(hdy) <= self.cfg.y_threshold:
            hand_text = "方向对准了，请向前伸手并轻轻抓取。"
        else:
            hand_text = f"请{x_move}，{y_move}。"

        return f"{head} {hand_text}", False
