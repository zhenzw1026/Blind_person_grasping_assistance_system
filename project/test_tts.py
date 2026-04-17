from __future__ import annotations

import time

from grasp_assist.audio.speaker import Speaker
from grasp_assist.config import load_config


def main():
    cfg = load_config("configs/default.yaml")
    spk = Speaker(
        interval_sec=0.1,
        rate=cfg.audio.rate,
        backend=getattr(cfg.audio, "tts_backend", "windows"),
        log_events=True,
    )

    lines = [
        "系统提示：语音测试开始。",
        "已识别目标，手机在左前方。",
        "请手向右移动，再向前伸手。",
        "您已经拿到手机。",
    ]

    for line in lines:
        spk.say(line, replace_pending=True, force=True)
        time.sleep(0.5)

    time.sleep(2.0)
    spk.close()
    print("TTS_TEST_DONE")


if __name__ == "__main__":
    main()
