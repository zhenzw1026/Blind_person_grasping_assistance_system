from __future__ import annotations

from pathlib import Path
from typing import Iterable

import cv2

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:  # pragma: no cover - optional dependency fallback
    Image = None
    ImageDraw = None
    ImageFont = None


class UnicodeTextRenderer:
    def __init__(self, enable_unicode: bool = True, font_path: str = "", font_size: int = 26):
        self.enable_unicode = enable_unicode and Image is not None
        self.font_size = max(12, int(font_size))
        self.font = None

        if self.enable_unicode:
            resolved = self._resolve_font_path(font_path)
            if resolved:
                try:
                    self.font = ImageFont.truetype(str(resolved), self.font_size)
                except OSError:
                    self.font = None

            if self.font is None:
                self.enable_unicode = False

    def _resolve_font_path(self, custom_path: str) -> Path | None:
        candidates = []
        if custom_path:
            candidates.append(Path(custom_path))

        candidates.extend(
            [
                Path("C:/Windows/Fonts/msyh.ttc"),
                Path("C:/Windows/Fonts/msyhbd.ttc"),
                Path("C:/Windows/Fonts/simhei.ttf"),
                Path("C:/Windows/Fonts/simsun.ttc"),
                Path("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"),
                Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
            ]
        )

        return self._first_existing(candidates)

    @staticmethod
    def _first_existing(paths: Iterable[Path]) -> Path | None:
        for path in paths:
            if path.exists():
                return path
        return None

    @staticmethod
    def _to_ascii_fallback(text: str) -> str:
        ascii_text = text.encode("ascii", "ignore").decode("ascii").strip()
        return ascii_text if ascii_text else "N/A"

    def put_text(
        self,
        frame,
        text: str,
        origin: tuple[int, int],
        color: tuple[int, int, int] = (255, 255, 255),
        font_scale: float = 0.7,
        thickness: int = 2,
    ):
        if self.enable_unicode and self.font is not None and Image is not None and ImageDraw is not None:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pil_img = Image.fromarray(rgb)
            draw = ImageDraw.Draw(pil_img)
            draw.text(
                origin,
                text,
                font=self.font,
                fill=(int(color[2]), int(color[1]), int(color[0])),
                stroke_width=max(0, int(thickness) - 1),
                stroke_fill=(0, 0, 0),
            )
            frame[:, :, :] = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
            return

        fallback_text = self._to_ascii_fallback(text)
        cv2.putText(frame, fallback_text, origin, cv2.FONT_HERSHEY_SIMPLEX, font_scale, color, thickness)


# Kept at bottom to avoid importing numpy when the module fails early on Pillow issues.
import numpy as np
