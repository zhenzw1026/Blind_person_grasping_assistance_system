from __future__ import annotations

import difflib
import os
import re
import tempfile
import threading
import time
import wave

import cv2
import numpy as np
import speech_recognition as sr
import whisper

from grasp_assist.audio.speaker import Speaker
from grasp_assist.config import AppConfig
from grasp_assist.detectors.hand_tracker import HandTracker
from grasp_assist.detectors.object_detector import build_object_detector
from grasp_assist.eval.metrics import MetricsTracker
from grasp_assist.eval.session_logger import SessionLogger
from grasp_assist.guidance.policy import GuidancePolicy
from grasp_assist.ui import UnicodeTextRenderer


def _clamp_int(v: float, lo: int, hi: int) -> int:
    return int(max(lo, min(hi, v)))


class GraspAssistPipeline:
    def __init__(self, cfg: AppConfig, enable_audio: bool = True):
        self.cfg = cfg
        self.hand_tracker = HandTracker(cfg.hand)
        self.object_detector = build_object_detector(cfg.obj)
        self.policy = GuidancePolicy(cfg.guidance)
        self.metrics = MetricsTracker()
        self.logger = SessionLogger(cfg.runtime.output_dir) if cfg.runtime.record_session else None
        self.text_renderer = UnicodeTextRenderer(
            enable_unicode=cfg.runtime.ui_enable_unicode,
            font_path=cfg.runtime.ui_font_path,
            font_size=cfg.runtime.ui_font_size,
        )
        self.speaker = (
            Speaker(
                interval_sec=cfg.audio.speech_interval_sec,
                rate=cfg.audio.rate,
                backend=getattr(cfg.audio, "tts_backend", "auto"),
                log_events=getattr(cfg.audio, "tts_log_events", False),
            )
            if (cfg.audio.enabled and enable_audio) else None
        )

        self.recognizer_backend = (cfg.audio.recognizer or "whisper").lower()
        self.whisper_language = (cfg.audio.language or "zh").lower()
        self.whisper_model_name = cfg.audio.whisper_model or "small"
        self.whisper_model = None
        self.use_whisper = False
        if self.recognizer_backend == "whisper":
            try:
                self.whisper_model = whisper.load_model(self.whisper_model_name)
                self.use_whisper = True
            except Exception as exc:
                raise RuntimeError(
                    f"无法加载Whisper模型 '{self.whisper_model_name}'：{exc}"
                ) from exc
        else:
            raise ValueError(f"不支持的语音识别后端: {self.recognizer_backend}")

        self.exit_keywords = ["结束", "退出", "停止", "关闭", "再见", "bye", "quit", "exit"]
        self.running = True
        self.is_grabbed = False
        self.just_grabbed = False
        self.current_target_en = None
        self.current_target_aliases: list[str] = []
        self.current_target_cn = "等待语音指令..."
        self.recognition_status = "正在监听..."
        self.listen_thread = None
        self.last_recognition_text = ""
        self.failed_attempts = 0
        self.max_failed_attempts = 3
        self.last_command_time = 0.0
        
        self.last_guidance_msg = ""
        self.last_guidance_time = 0.0
        self.guidance_interval = max(0.6, float(getattr(cfg.audio, "min_guidance_interval_sec", 2.0)))
        self.guidance_repeat_interval = max(
            self.guidance_interval + 1.0,
            float(getattr(cfg.audio, "guidance_repeat_sec", 5.0)),
        )
        self._warned_whisper_runtime = False
        self.user_reaction_until = 0.0
        self.detect_interval_frames = max(1, int(getattr(cfg.obj, "detect_interval_frames", 1)))
        self.obj_lost_tolerance = max(0, int(getattr(cfg.obj, "max_lost_frames", 3)))
        self._obj_lost_count = 0
        self._cached_obj_pt = None
        self._cached_obj_box = None
        self._cached_obj_label = None
        self._cached_obj_conf = 0.0

        self.traditional_to_simplified = {
            "電": "电", "話": "话", "機": "机", "錄": "录", "鍵": "键", "鏡": "镜", "書": "书",
            "雜": "杂", "誌": "志", "遙": "遥", "燈": "灯", "門": "门", "戶": "户", "牆": "墙",
            "發": "发", "雙": "双", "鴨": "鸭", "襪": "袜", "幫": "帮", "錶": "表", "國": "国",
            "長": "长", "結": "结", "體": "体", "語": "语", "請": "请", "給": "给",
        }

        self.target_catalog = {
            "手机": {
                "primary": "cell phone",
                "aliases": ["mobile phone", "phone", "smartphone"],
                "spoken": ["手机", "電話", "电话", "手機", "移动电话", "手机壳"],
            },
            "杯子": {
                "primary": "cup",
                "aliases": ["mug", "glass"],
                "spoken": ["杯子", "水杯", "玻璃杯", "杯", "马克杯"],
            },
            "瓶子": {
                "primary": "bottle",
                "aliases": ["water bottle"],
                "spoken": ["瓶子", "水瓶", "矿泉水", "瓶"],
            },
            "键盘": {
                "primary": "keyboard",
                "aliases": [],
                "spoken": ["键盘", "鍵盤"],
            },
            "鼠标": {
                "primary": "mouse",
                "aliases": ["computer mouse"],
                "spoken": ["鼠标", "滑鼠", "鼠"],
            },
            "眼镜": {
                "primary": "glasses",
                "aliases": ["eyeglasses", "spectacles"],
                "spoken": ["眼镜", "眼鏡", "墨镜"],
            },
            "剪刀": {
                "primary": "scissors",
                "aliases": [],
                "spoken": ["剪刀", "剪子"],
            },
            "钥匙": {
                "primary": "key",
                "aliases": ["keys"],
                "spoken": ["钥匙", "锁匙", "门钥匙", "鑰匙"],
            },
            "书": {
                "primary": "book",
                "aliases": [],
                "spoken": ["书", "書", "书本", "课本"],
            },
            "遥控器": {
                "primary": "remote",
                "aliases": ["remote control"],
                "spoken": ["遥控器", "遙控器", "遥控"],
            },
            "苹果": {
                "primary": "apple",
                "aliases": [],
                "spoken": ["苹果", "蘋果"],
            },
            "手表": {
                "primary": "watch",
                "aliases": ["wristwatch"],
                "spoken": ["手表", "手錶", "表", "腕表"],
            },
        }

        # backward compatibility for existing scripts
        self.label_map_cn2en: dict[str, str] = {}
        self.alias_to_target: dict[str, str] = {}
        for cn_name, meta in self.target_catalog.items():
            primary = str(meta["primary"]).lower().strip()
            self.label_map_cn2en[cn_name] = primary
            aliases = [cn_name, *meta.get("spoken", [])]
            for alias in aliases:
                norm = self._normalize_spoken_text(alias)
                if not norm:
                    continue
                self.label_map_cn2en[alias] = primary
                self.alias_to_target[norm] = cn_name
        
    def simplified_chinese(self, text: str) -> str:
        return "".join(self.traditional_to_simplified.get(char, char) for char in text)

    def _normalize_spoken_text(self, text: str) -> str:
        txt = self.simplified_chinese((text or "").strip().lower())
        txt = re.sub(r"[\s\u3000]+", "", txt)
        txt = re.sub(r"[，。！？、,.!?;；:：\-\_\(\)\[\]{}\"'`~]", "", txt)
        return txt

    def _strip_command_prefix(self, text: str) -> str:
        cleaned = text
        for token in ["帮我", "我要", "我想", "请", "给我", "一下", "找", "查找", "看看", "定位", "拿", "拿到"]:
            cleaned = cleaned.replace(token, "")
        return cleaned

    def _extract_target_with_aliases(self, text: str) -> tuple[str | None, str | None, list[str]]:
        normalized = self._normalize_spoken_text(text)
        normalized = self._strip_command_prefix(normalized)
        if not normalized:
            return None, None, []

        # exact / contains matching first
        alias_items = sorted(self.alias_to_target.items(), key=lambda kv: len(kv[0]), reverse=True)
        for alias, cn_name in alias_items:
            if alias and alias in normalized:
                meta = self.target_catalog[cn_name]
                primary = str(meta["primary"]).lower().strip()
                aliases = [a.lower().strip() for a in meta.get("aliases", []) if a]
                return cn_name, primary, aliases

        # fuzzy fallback for ASR glitches
        best_cn = None
        best_score = 0.0
        samples = [normalized]
        if len(normalized) >= 2:
            samples.extend([normalized[-2:], normalized[-3:], normalized[-4:]])

        for alias, cn_name in alias_items:
            if len(alias) < 2:
                continue
            for sample in samples:
                score = difflib.SequenceMatcher(None, alias, sample).ratio()
                if score > best_score:
                    best_score = score
                    best_cn = cn_name

        if best_cn and best_score >= 0.72:
            meta = self.target_catalog[best_cn]
            primary = str(meta["primary"]).lower().strip()
            aliases = [a.lower().strip() for a in meta.get("aliases", []) if a]
            print(f"[模糊匹配] {text} -> {best_cn} ({best_score:.2f})")
            return best_cn, primary, aliases

        return None, None, []

    def extract_target_from_text(self, text: str) -> tuple[str | None, str | None]:
        cn_name, en_name, _ = self._extract_target_with_aliases(text)
        return cn_name, en_name

    @staticmethod
    def _clean_recognition_text(text: str) -> str:
        cleaned = (text or "").strip()
        cleaned = cleaned.replace("\n", " ")
        cleaned = re.sub(r"\s+", " ", cleaned)
        return cleaned

    @staticmethod
    def _wrap_text(text: str, max_chars: int = 16, max_lines: int = 2) -> list[str]:
        if not text:
            return [""]
        max_chars = max(6, int(max_chars))
        chunks: list[str] = []
        current = ""
        for ch in text:
            current += ch
            if len(current) >= max_chars:
                chunks.append(current)
                current = ""
        if current:
            chunks.append(current)
        if len(chunks) > max_lines:
            merged = chunks[:max_lines]
            merged[-1] = merged[-1][:-1] + "…"
            return merged
        return chunks

    def _contains_any(self, text: str, words: list[str]) -> bool:
        for w in words:
            if w and w in text:
                return True
        return False

    def _estimate_speech_duration(self, text: str) -> float:
        chars = len(self.simplified_chinese(text or ""))
        rate = max(120, int(self.cfg.audio.rate))
        chars_per_sec = max(2.4, rate / 55.0)
        return min(8.0, max(1.0, chars / chars_per_sec))

    def _set_user_reaction_window(self, text: str, extra_sec: float = 0.0):
        base = max(0.5, float(getattr(self.cfg.audio, "reaction_grace_sec", 1.4)))
        duration = self._estimate_speech_duration(text)
        self.user_reaction_until = max(self.user_reaction_until, time.perf_counter() + duration + base + extra_sec)

    def _say(
        self,
        text: str,
        *,
        replace_pending: bool = True,
        force: bool = True,
        hold_for_reply: bool = True,
        extra_reaction_sec: float = 0.0,
    ):
        if not self.speaker:
            return
        self.speaker.say(text, replace_pending=replace_pending, force=force)
        if hold_for_reply:
            self._set_user_reaction_window(text, extra_sec=extra_reaction_sec)

    def _audio_to_temp_file(self, audio: sr.AudioData) -> str:
        raw = audio.get_raw_data(convert_rate=16000, convert_width=2)
        pcm = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
        if pcm.size > 0:
            peak = float(np.max(np.abs(pcm)))
            if peak > 0:
                pcm = pcm / peak
            rms = float(np.sqrt(np.mean(np.square(pcm))))
            gain = 1.0
            if rms < 0.06:
                gain = min(2.2, 0.11 / max(rms, 1e-6))
            pcm = np.clip(pcm * gain, -1.0, 1.0)

        out_pcm = (pcm * 32767.0).astype(np.int16).tobytes()
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            temp_path = tmp.name

        with wave.open(temp_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(out_pcm)
        return temp_path

    def _transcribe_with_whisper(self, audio: sr.AudioData) -> str:
        if self.whisper_model is None:
            raise RuntimeError("Whisper 模型尚未初始化")

        temp_path = None
        try:
            temp_path = self._audio_to_temp_file(audio)

            result = self.whisper_model.transcribe(
                temp_path,
                language=self.whisper_language,
                task="transcribe",
                fp16=False,
                temperature=float(self.cfg.audio.whisper_temperature),
                beam_size=max(1, int(self.cfg.audio.whisper_beam_size)),
                best_of=max(1, int(self.cfg.audio.whisper_best_of)),
                condition_on_previous_text=False,
                initial_prompt=self.cfg.audio.whisper_initial_prompt or None,
            )
            return self._clean_recognition_text(result.get("text") or "")
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass

    def _transcribe_audio(self, recognizer: sr.Recognizer, audio: sr.AudioData) -> str:
        whisper_exc = None
        text = ""
        if self.use_whisper and self.whisper_model is not None:
            try:
                text = self._transcribe_with_whisper(audio)
                if text:
                    print(f"[Whisper识别] {text}")
                    return text
            except Exception as exc:
                whisper_exc = exc
                err_text = str(exc)
                if "WinError 2" in err_text or "No such file or directory" in err_text:
                    self.use_whisper = False
                    if not self._warned_whisper_runtime:
                        print("[警告] Whisper运行依赖缺失，自动切换到Google识别以保证实时性。")
                        self._warned_whisper_runtime = True
                else:
                    print(f"[警告] Whisper识别失败: {exc}")

        if self.cfg.audio.fallback_google:
            try:
                text = recognizer.recognize_google(audio, language=self.cfg.audio.google_language)
                text = self._clean_recognition_text(text)
                if text:
                    print(f"[Google识别] {text}")
                    return text
            except sr.UnknownValueError:
                pass
            except sr.RequestError as exc:
                print(f"[警告] Google识别不可用: {exc}")

        if whisper_exc is not None:
            raise RuntimeError(str(whisper_exc))
        return ""

    def _apply_target(self, target_cn: str, target_en: str, target_aliases: list[str]):
        self.current_target_cn = target_cn
        self.current_target_en = target_en
        self.current_target_aliases = list(target_aliases)

        if hasattr(self.object_detector, "set_target_class"):
            self.object_detector.set_target_class(target_en, aliases=target_aliases)
        elif hasattr(self.object_detector, "target_class"):
            self.object_detector.target_class = target_en

        self.is_grabbed = False
        self.just_grabbed = False
        self.failed_attempts = 0
        self.last_guidance_msg = ""
        self.last_guidance_time = 0.0
        self._cached_obj_pt = None
        self._cached_obj_box = None
        self._cached_obj_label = None
        self._cached_obj_conf = 0.0
        self._obj_lost_count = 0

    def listen_for_command(self):
        """持续监听麦克风，随时可以说话"""
        r = sr.Recognizer()
        r.dynamic_energy_threshold = bool(self.cfg.audio.dynamic_energy_threshold)
        r.energy_threshold = max(50, int(self.cfg.audio.energy_threshold))
        r.pause_threshold = max(0.3, float(self.cfg.audio.pause_threshold))
        r.non_speaking_duration = max(0.15, float(self.cfg.audio.non_speaking_duration))

        try:
            with sr.Microphone() as source:
                print("[系统] 开始麦克风监听...")
                r.adjust_for_ambient_noise(source, duration=max(0.4, float(self.cfg.audio.ambient_adjust_sec)))
                print("[系统] 麦克风已调整（语言：普通话）")

                while self.running:
                    try:
                        if time.perf_counter() < self.user_reaction_until:
                            time.sleep(0.05)
                            continue

                        self.recognition_status = "正在监听..."
                        audio = r.listen(
                            source,
                            timeout=max(2.0, float(self.cfg.audio.listen_timeout)),
                            phrase_time_limit=max(1.5, float(self.cfg.audio.phrase_time_limit)),
                        )
                        self.recognition_status = "正在识别..."
                        text = self._transcribe_audio(r, audio)

                        if not text:
                            self.recognition_status = "正在监听..."
                            self.failed_attempts = 0
                            continue

                        self.last_recognition_text = self.simplified_chinese(text)
                        normalized_text = self._normalize_spoken_text(self.last_recognition_text)
                        print(f"[识别文本] {self.last_recognition_text}")

                        if time.perf_counter() - self.last_command_time < float(self.cfg.audio.command_cooldown_sec):
                            continue

                        if any(word in normalized_text for word in self.exit_keywords):
                            print("[系统] 检测到退出命令")
                            self.running = False
                            self.recognition_status = "系统关闭中"
                            if self.speaker:
                                self._say("系统关闭，感谢使用。", extra_reaction_sec=0.2)
                            break

                        target_cn, target_en, target_aliases = self._extract_target_with_aliases(text)
                        if target_cn and target_en:
                            # Avoid repeating confirmation speech when user repeats the same command.
                            if self.current_target_cn == target_cn and not self.is_grabbed:
                                self.recognition_status = f"继续找: {target_cn}"
                                self.last_command_time = time.perf_counter()
                                continue

                            self._apply_target(target_cn, target_en, target_aliases)
                            self.recognition_status = f"正在找: {target_cn}"
                            self.last_command_time = time.perf_counter()
                            confirm_msg = f"好的，开始帮你找{target_cn}。请把手伸到镜头前。"
                            print(f"[反馈] {confirm_msg}")
                            if self.speaker:
                                self._say(confirm_msg, extra_reaction_sec=0.4)
                        else:
                            # During active guidance, do not keep speaking recognition failures.
                            if self.current_target_en is not None and not self.is_grabbed:
                                self.recognition_status = f"继续找: {self.current_target_cn}"
                                continue

                            if any(word in normalized_text for word in ["找", "帮", "我要", "查"]):
                                self.failed_attempts += 1
                                if self.failed_attempts < self.max_failed_attempts:
                                    self.recognition_status = "我听到了，但没听清物品名"
                                    if self.speaker:
                                        self._say("我听到了找东西的指令，但没听清物品名称，请再说一遍。", extra_reaction_sec=0.4)
                                else:
                                    self.recognition_status = "无法识别物品，请重试"
                                    if self.speaker:
                                        self._say("抱歉，还是没有识别出物品名称，请慢一点再说一次。", extra_reaction_sec=0.5)
                                    self.failed_attempts = 0
                            else:
                                self.failed_attempts += 1
                                if self.failed_attempts >= self.max_failed_attempts:
                                    self.recognition_status = "无法识别物品，请重试"
                                    if self.speaker:
                                        self._say("请直接说物品名，例如手机、杯子、钥匙。", extra_reaction_sec=0.4)
                                    self.failed_attempts = 0

                    except sr.WaitTimeoutError:
                        self.recognition_status = "正在监听..."

                    except sr.RequestError as exc:
                        print(f"[网络错误] {exc}")
                        self.recognition_status = "语音服务不可用"
                        if self.speaker:
                            self._say("语音服务暂时不可用，请稍后重试。", extra_reaction_sec=0.4)
                        time.sleep(1.5)

                    except Exception as exc:
                        print(f"[识别异常] {exc}")
                        self.recognition_status = "识别异常，请重试"
                        self.failed_attempts += 1

        except Exception as exc:
            print(f"[致命错误] {exc}")
            self.recognition_status = "麦克风异常"
            if self.speaker:
                self._say("麦克风出现问题，请检查设备。", extra_reaction_sec=0.4)

    def run(self, source=None, display: bool | None = None):
        if source is None:
            source = self.cfg.camera.index

        cv2.setUseOptimized(True)
        try:
            cv2.setNumThreads(2)
        except Exception:
            pass

        cap = cv2.VideoCapture(source, cv2.CAP_DSHOW) if isinstance(source, int) else cv2.VideoCapture(source)
        if isinstance(source, int):
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.cfg.camera.width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.cfg.camera.height)
            
        if not cap.isOpened():
            raise RuntimeError("Cannot open webcam")

        show = self.cfg.runtime.display if display is None else display
        frame_id = 0

        print("[启动] 启动语音监听线程...")
        self.listen_thread = threading.Thread(target=self.listen_for_command, daemon=True)
        self.listen_thread.start()
        time.sleep(0.5)

        if self.speaker:
            welcome_msg = "系统启动完成。请说：帮我找手机，或者帮我找杯子。"
            print(f"[欢迎] {welcome_msg}")
            self._say(welcome_msg, extra_reaction_sec=0.8)

        try:
            while self.running:
                loop_start = time.perf_counter()
                ok, frame = cap.read()
                if not ok:
                    break
                frame_id += 1

                frame = cv2.flip(frame, 1)
                h, w = frame.shape[:2]
                hand_pt, hand_result = self.hand_tracker.detect_index_tip(frame)

                obj_pt, obj_box, obj_label, obj_conf = None, None, None, 0.0
                msg = "请先说出要找的物品，例如：帮我找手机。"

                if self.current_target_en is not None:
                    if not self.is_grabbed:
                        if frame_id % self.detect_interval_frames == 0 or self._cached_obj_box is None:
                            det_pt, det_box, det_label, det_conf = self.object_detector.detect(frame)
                            if det_box is not None:
                                self._cached_obj_pt = det_pt
                                self._cached_obj_box = det_box
                                self._cached_obj_label = det_label
                                self._cached_obj_conf = det_conf
                                self._obj_lost_count = 0
                            else:
                                self._obj_lost_count += 1
                                if self._obj_lost_count > self.obj_lost_tolerance:
                                    self._cached_obj_pt = None
                                    self._cached_obj_box = None
                                    self._cached_obj_label = None
                                    self._cached_obj_conf = 0.0

                            obj_pt = self._cached_obj_pt
                            obj_box = self._cached_obj_box
                            obj_label = self._cached_obj_label
                            obj_conf = self._cached_obj_conf
                        else:
                            obj_pt = self._cached_obj_pt
                            obj_box = self._cached_obj_box
                            obj_label = self._cached_obj_label
                            obj_conf = self._cached_obj_conf

                        msg, grabbed = self.policy.generate(
                            hand_pt,
                            obj_pt,
                            obj_box,
                            obj_label,
                            w,
                            h,
                            target_cn=self.current_target_cn,
                        )

                        if grabbed:
                            self.is_grabbed = True
                            self.just_grabbed = True
                            print(f"[成功] 已拿到 {self.current_target_cn}")
                    else:
                        msg = f"已拿到 {self.current_target_cn}，请说下一个物品。"

                if self.speaker:
                    if self.just_grabbed:
                        grabbed_name = self.current_target_cn
                        grabbed_msg = f"您已经拿到{grabbed_name}。请说下一个要找的物品。"
                        print(f"[播报] {grabbed_msg}")
                        try:
                            self._say(grabbed_msg, extra_reaction_sec=1.0)
                        except Exception as exc:
                            print(f"[错误] 播报失败: {exc}")
                        self.just_grabbed = False
                        self.current_target_en = None
                        self.current_target_aliases = []
                        self.current_target_cn = "等待语音指令..."
                        self.is_grabbed = False
                        self.last_guidance_msg = ""
                    elif not self.is_grabbed and self.current_target_en is not None:
                        current_time = time.perf_counter()
                        gap = current_time - self.last_guidance_time
                        should_repeat = gap >= self.guidance_repeat_interval
                        if gap >= self.guidance_interval and (msg != self.last_guidance_msg or should_repeat):
                            print(f"[方向] {msg}")
                            try:
                                # Guidance should not be muted by stale queue items.
                                self._say(msg, extra_reaction_sec=0.2)
                            except Exception as exc:
                                print(f"[错误] 播报方向失败: {exc}")
                            self.last_guidance_msg = msg
                            self.last_guidance_time = current_time

                latency_ms = (time.perf_counter() - loop_start) * 1000.0

                self.metrics.update(latency_ms, hand_pt is not None, obj_pt is not None, msg)

                if self.logger:
                    self.logger.log_frame(frame_id, latency_ms, hand_pt is not None, obj_pt is not None, obj_label, obj_conf, msg)

                if show:
                    self._draw(frame, hand_pt, hand_result, obj_pt, obj_box, obj_label, obj_conf, msg, latency_ms)
                    cv2.imshow(self.cfg.runtime.window_name, frame)

                    key = cv2.waitKey(1) & 0xFF
                    if key == 27 or key == ord("q"):
                        print("[用户] 按下ESC，程序退出")
                        self.running = False
                        break
        
        except KeyboardInterrupt:
            print("[用户] 按下Ctrl+C，程序退出")
            self.running = False

        finally:
            print("[关闭] 清理资源...")
            if self.speaker:
                self.speaker.close()
            self.hand_tracker.close()
            cap.release()
            if show:
                cv2.destroyAllWindows()

            summary = self.metrics.summary()
            if self.logger:
                self.logger.log_summary(summary)
                self.logger.close()

            return summary

    def _draw(self, frame, hand_pt, hand_result, obj_pt, obj_box, obj_label, obj_conf, msg, latency_ms):
        if hand_result and hand_result.multi_hand_landmarks:
            for lm in hand_result.multi_hand_landmarks:
                for landmark in lm.landmark:
                    x = int(landmark.x * frame.shape[1])
                    y = int(landmark.y * frame.shape[0])
                    if 0 <= x < frame.shape[1] and 0 <= y < frame.shape[0]:
                        cv2.circle(frame, (x, y), 2, (200, 100, 200), -1)

        if hand_pt is not None:
            cv2.circle(frame, hand_pt, 8, (0, 0, 255), -1)

        if obj_box is not None:
            x, y, w, h = obj_box
            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
            if obj_pt is not None:
                cv2.circle(frame, obj_pt, 8, (0, 255, 0), -1)

            px, py = int(max(30, w * 0.3)), int(max(30, h * 0.3))
            cv2.rectangle(frame, (x - px, y - py), (x + w + px, y + h + py), (0, 100, 255), 1)

            if obj_label:
                label_text = f"{obj_label} {obj_conf:.2f}"
            else:
                label_text = f"目标 {obj_conf:.2f}"
            cv2.putText(frame, label_text, (max(5, x - 5), max(20, y - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

        if hand_pt is not None and obj_pt is not None:
            cv2.line(frame, hand_pt, obj_pt, (0, 255, 255), 2)

        # translucent panels for readable UI
        h_img, w_img = frame.shape[:2]
        margin = 10
        panel_gap = 12
        right_panel_w = max(260, min(360, int(w_img * 0.32)))
        right_panel_x = w_img - margin - right_panel_w
        left_panel_x = margin
        left_panel_w = max(280, right_panel_x - left_panel_x - panel_gap)
        left_panel_h = 156
        right_panel_h = 108
        overlay = frame.copy()
        cv2.rectangle(overlay, (left_panel_x, margin), (left_panel_x + left_panel_w, margin + left_panel_h), (25, 25, 25), -1)
        cv2.rectangle(overlay, (right_panel_x, margin), (right_panel_x + right_panel_w, margin + right_panel_h), (25, 25, 25), -1)
        cv2.addWeighted(overlay, 0.45, frame, 0.55, 0, frame)

        target_text = self.current_target_cn if self.current_target_cn else "未设置"
        guide_text = self.simplified_chinese(msg or "")
        self.text_renderer.put_text(frame, f"目标: {target_text}", (left_panel_x + 14, margin + 12), (0, 240, 255), 0.8, 2)
        self.text_renderer.put_text(frame, "指导:", (left_panel_x + 14, margin + 44), (70, 170, 255), 0.74, 2)
        max_chars = max(10, (left_panel_w - 70) // 22)
        guide_lines = self._wrap_text(guide_text, max_chars=max_chars, max_lines=3)
        y0 = margin + 44
        for i, line in enumerate(guide_lines):
            self.text_renderer.put_text(frame, line, (left_panel_x + 86, y0 + i * 30), (70, 170, 255), 0.72, 2)
        self.text_renderer.put_text(frame, f"延迟: {latency_ms:.0f} ms", (left_panel_x + 14, margin + left_panel_h - 32), (120, 220, 120), 0.72, 2)

        h_img, w_img = frame.shape[:2]
        color = (0, 165, 255) if "正在识别" in self.recognition_status else (0, 255, 0)
        if "正在监听" in self.recognition_status:
            status_display = "语音: 监听中"
        elif "正在识别" in self.recognition_status:
            status_display = "语音: 识别中"
        else:
            status_display = f"语音: {self.simplified_chinese(self.recognition_status)[:12]}"
        self.text_renderer.put_text(frame, status_display, (right_panel_x + 12, margin + 12), color, 0.7, 2)

        if self.last_recognition_text:
            display_text = self.simplified_chinese(self.last_recognition_text)[:14]
            self.text_renderer.put_text(frame, f"识别: {display_text}", (right_panel_x + 12, margin + 48), (120, 200, 255), 0.7, 2)

        cv2.circle(frame, (_clamp_int(w_img - 28, 0, w_img - 1), 28), 8, color, -1)
