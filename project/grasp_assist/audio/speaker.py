from __future__ import annotations

import ctypes
import queue
import subprocess
import sys
import threading
import time

import pyttsx3


class Speaker:
    def __init__(
        self,
        interval_sec: float = 1.2,
        rate: int = 180,
        backend: str = "auto",
        log_events: bool = False,
    ):
        self.interval_sec = interval_sec
        self.rate = int(rate)
        self.backend = (backend or "auto").lower().strip()
        self.log_events = bool(log_events)
        self.last_spoken = ""
        self.last_time = 0.0
        self.q: queue.Queue[str | None] = queue.Queue(maxsize=8)
        self._lock = threading.Lock()
        if self.backend == "auto":
            self.backend = "pyttsx3"

        if self.log_events:
            print(f"[TTS] backend={self.backend}, rate={self.rate}")

        self.worker = threading.Thread(target=self._run, daemon=True)
        self.worker.start()

    def _reset_engine(self):
        # Keep API for compatibility; one-shot engine does not need persistent reset.
        return

    @staticmethod
    def _co_initialize_if_needed() -> bool:
        if not sys.platform.startswith("win"):
            return False
        try:
            ctypes.windll.ole32.CoInitialize(None)
            return True
        except Exception:
            return False

    @staticmethod
    def _co_uninitialize_if_needed(inited: bool):
        if not inited:
            return
        try:
            ctypes.windll.ole32.CoUninitialize()
        except Exception:
            pass

    def _speak_with_windows_tts(self, msg: str) -> bool:
        if not sys.platform.startswith("win"):
            return False
        safe = msg.replace("'", "''")
        cmd = (
            "Add-Type -AssemblyName System.Speech; "
            "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            "$s.Volume=100; "
            "$s.Rate=0; "
            f"$s.Speak('{safe}');"
        )
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", cmd],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            ok = result.returncode == 0
            if self.log_events:
                print(f"[TTS] windows speak {'ok' if ok else 'failed'}")
            return ok
        except Exception:
            return False

    def _speak_with_pyttsx3(self, msg: str) -> bool:
        engine = None
        try:
            # One-shot engine per utterance avoids the common Windows issue where
            # a shared pyttsx3 engine only speaks the first sentence.
            engine = pyttsx3.init()
            engine.setProperty("rate", self.rate)
            engine.say(msg)
            engine.runAndWait()
            if self.log_events:
                print("[TTS] pyttsx3 speak ok")
            return True
        except Exception as exc:
            print(f"[TTS异常] {exc}")
            try:
                engine = pyttsx3.init()
                engine.setProperty("rate", self.rate)
                engine.say(msg)
                engine.runAndWait()
                if self.log_events:
                    print("[TTS] pyttsx3 retry ok")
                return True
            except Exception as exc2:
                print(f"[TTS重试失败] {exc2}")
                return False
        finally:
            if engine is not None:
                try:
                    engine.stop()
                except Exception:
                    pass

    def _speak(self, msg: str) -> bool:
        if self.backend == "windows":
            return self._speak_with_windows_tts(msg) or self._speak_with_pyttsx3(msg)
        if self.backend == "pyttsx3":
            return self._speak_with_pyttsx3(msg) or self._speak_with_windows_tts(msg)
        return self._speak_with_pyttsx3(msg) or self._speak_with_windows_tts(msg)

    def _run(self):
        coinited = self._co_initialize_if_needed()
        try:
            while True:
                msg = self.q.get()
                if msg is None:
                    break
                if not msg:
                    continue
                if self.log_events:
                    print(f"[TTS] speaking: {msg}")
                ok = self._speak(msg)
                if not ok:
                    print("[TTS失败] 当前语音后端均不可用")
        finally:
            self._co_uninitialize_if_needed(coinited)

    def _drain_pending(self):
        while True:
            try:
                item = self.q.get_nowait()
            except queue.Empty:
                break
            if item is None:
                # Preserve shutdown sentinel if encountered.
                self.q.put(None)
                break

    def say(self, msg: str, *, replace_pending: bool = False, force: bool = False):
        if not msg:
            return

        now = time.time()
        if (not force) and msg == self.last_spoken and now - self.last_time < self.interval_sec:
            return

        with self._lock:
            if replace_pending:
                self._drain_pending()
            self.last_spoken = msg
            self.last_time = now
            if not self.worker.is_alive():
                # Recover from unexpected worker termination.
                self.worker = threading.Thread(target=self._run, daemon=True)
                self.worker.start()
                if self.log_events:
                    print("[TTS] worker restarted")

            try:
                self.q.put_nowait(msg)
                if self.log_events:
                    print("[TTS] queued")
            except queue.Full:
                # Drop the oldest pending item to keep guidance real-time.
                try:
                    _ = self.q.get_nowait()
                except queue.Empty:
                    pass
                try:
                    self.q.put_nowait(msg)
                    if self.log_events:
                        print("[TTS] queue full, dropped oldest")
                except queue.Full:
                    pass

    def close(self):
        try:
            self.q.put_nowait(None)
        except queue.Full:
            self._drain_pending()
            self.q.put_nowait(None)
