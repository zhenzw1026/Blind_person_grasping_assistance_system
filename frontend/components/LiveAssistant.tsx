"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { resetSession, sendFrame, sendVoiceCommand, startSession, updateSettings } from "@/lib/api";
import { defaultSettings, loadSettings } from "@/lib/settings";
import { AppSettings, GuideState } from "@/types/api";

const RATE_MAP: Record<string, number> = { slow: 0.85, medium: 1, fast: 1.2 };
const TARGET_PROMPT = "\u8bf7\u8bf4\u51fa\u4f60\u8981\u627e\u7684\u7269\u54c1";

type InputMode = "ptt" | "continuous";
type CapturedFrame = { imageB64: string; width: number; height: number };
type AnnouncementItem = { text: string; ts: number };

const CN_FIND = /(?:\u5e2e\u6211\u627e|\u8bf7\u5e2e\u6211\u627e|\u5bfb\u627e|\u6211\u8981\u627e|\u627e)(?<target>[\u4e00-\u9fa5a-zA-Z0-9]+)/;

declare global {
  interface Window {
    webkitSpeechRecognition?: any;
    SpeechRecognition?: any;
  }
}

export default function LiveAssistant() {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const captureCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const recognitionRef = useRef<any>(null);
  const frameTickerRef = useRef<number | null>(null);

  const runningRef = useRef(false);
  const waitingTargetRef = useRef(false);
  const speakingRef = useRef(false);
  const voicesReadyRef = useRef(false);
  const sessionIdRef = useRef("");
  const runTokenRef = useRef(0);
  const frameInFlightRef = useRef(false);
  const mirrorXRef = useRef(true);
  const lastInstructionChangeAtRef = useRef(0);
  const lastSpeakAtRef = useRef(0);
  const settingsRef = useRef<AppSettings>(defaultSettings);
  const inputModeRef = useRef<InputMode>("continuous");
  const instructionRef = useRef(TARGET_PROMPT);
  const lastAnnouncedRef = useRef("");
  const recentAnnouncementsRef = useRef<AnnouncementItem[]>([]);
  const pendingAnnouncementRef = useRef<string | null>(null);
  const autoStartedRef = useRef(false);
  const skipModeEffectRef = useRef(false);
  const speechEnabledRef = useRef(true);
  const recognitionActiveRef = useRef(false);
  const restartTimerRef = useRef<number | null>(null);
  const lastRecognitionStartAtRef = useRef(0);
  const ttsTailIgnoreUntilRef = useRef(0);

  const [settings, setSettings] = useState<AppSettings>(defaultSettings);
  const [sessionId, setSessionId] = useState("");
  const [targetInput, setTargetInput] = useState("");
  const [status, setStatus] = useState("\u672a\u542f\u52a8");
  const [instruction, setInstruction] = useState(TARGET_PROMPT);
  const [state, setState] = useState<GuideState>("searching");
  const [listening, setListening] = useState(false);
  const [ttsSupported, setTtsSupported] = useState(true);
  const [inputMode, setInputMode] = useState<InputMode>("continuous");
  const [recognizerState, setRecognizerState] = useState("idle");

  useEffect(() => {
    const loaded = loadSettings();
    setSettings(loaded);
    settingsRef.current = loaded;

    const supported = typeof window !== "undefined" && "speechSynthesis" in window;
    setTtsSupported(supported);

    if (supported) {
      const warm = () => {
        voicesReadyRef.current = window.speechSynthesis.getVoices().length > 0;
      };
      warm();
      window.speechSynthesis.onvoiceschanged = warm;
    }
  }, []);

  useEffect(() => {
    settingsRef.current = settings;
  }, [settings]);

  useEffect(() => {
    sessionIdRef.current = sessionId;
  }, [sessionId]);

  useEffect(() => {
    instructionRef.current = instruction;
  }, [instruction]);

  useEffect(() => {
    inputModeRef.current = inputMode;
    if (skipModeEffectRef.current) {
      skipModeEffectRef.current = false;
      return;
    }
    if (!runningRef.current) return;
    restartRecognitionForMode();
  }, [inputMode]);

  useEffect(() => {
    return () => {
      if (restartTimerRef.current) {
        window.clearTimeout(restartTimerRef.current);
        restartTimerRef.current = null;
      }
      stopFrameTicker();
      recognitionRef.current?.stop?.();
      stopCamera();
    };
  }, []);

  useEffect(() => {
    if (autoStartedRef.current) return;
    autoStartedRef.current = true;
    void startAll();
  }, []);

  async function startAll() {
    if (runningRef.current) return;

    try {
      speechEnabledRef.current = true;
      const token = runTokenRef.current + 1;
      runTokenRef.current = token;
      runningRef.current = true;
      waitingTargetRef.current = true;
      setSessionId("");
      setTargetInput("");
      setState("searching");
      setStatus(TARGET_PROMPT);
      setInstruction(TARGET_PROMPT);

      await startCamera(settingsRef.current.cameraId);
      if (token !== runTokenRef.current || !runningRef.current) return;

      if (recognitionRef.current) {
        try {
          recognitionRef.current.stop?.();
        } catch {
          // noop
        }
        recognitionRef.current = null;
        recognitionActiveRef.current = false;
      }

      setupRecognition(inputModeRef.current, inputModeRef.current === "continuous");
      announce(TARGET_PROMPT, true);
      window.setTimeout(() => {
        if (token === runTokenRef.current && runningRef.current) {
          announce(TARGET_PROMPT, false);
        }
      }, 500);
    } catch (error) {
      runningRef.current = false;
      setStatus(`\u542f\u52a8\u5931\u8d25: ${(error as Error).message}`);
    }
  }

  function stopAll() {
    speechEnabledRef.current = false;
    runTokenRef.current += 1;
    runningRef.current = false;
    waitingTargetRef.current = false;
    stopFrameTicker();
    recognitionRef.current?.stop?.();
    recognitionRef.current = null;
    recognitionActiveRef.current = false;
    if (restartTimerRef.current) {
      window.clearTimeout(restartTimerRef.current);
      restartTimerRef.current = null;
    }
    stopCamera();
    setListening(false);
    setSessionId("");
    setStatus("\u5df2\u505c\u6b62");
    setInstruction("\u5df2\u505c\u6b62\u5f15\u5bfc");
    pendingAnnouncementRef.current = null;
    announce("\u5df2\u505c\u6b62\u5f15\u5bfc", true);
    setRecognizerState("stopped");
  }

  async function resetAll() {
    if (!runningRef.current) return;

    if (!sessionIdRef.current) {
      waitingTargetRef.current = true;
      setInstruction(TARGET_PROMPT);
      setStatus(TARGET_PROMPT);
      announce(TARGET_PROMPT, true);
      return;
    }

    try {
      const token = runTokenRef.current;
      await resetSession(sessionIdRef.current);
      if (token !== runTokenRef.current || !runningRef.current) return;
      setState("searching");
      setStatus("\u5df2\u91cd\u7f6e\uff0c\u91cd\u65b0\u641c\u7d22\u4e2d");
      setInstruction(`\u5f00\u59cb\u641c\u7d22${targetInput}`);
      announce("\u5df2\u91cd\u7f6e\uff0c\u91cd\u65b0\u641c\u7d22", true);
    } catch (error) {
      setStatus(`\u91cd\u7f6e\u5931\u8d25: ${(error as Error).message}`);
    }
  }

  async function startTaskForTarget(target: string, token: number) {
    if (token !== runTokenRef.current || !runningRef.current) return;
    const session = await startSession(target);
    if (token !== runTokenRef.current || !runningRef.current) return;
    setSessionId(session.session_id);
    setTargetInput(target);
    setState(session.state);
    setInstruction(session.current_instruction);
    setStatus(`\u6536\u5230\uff0c\u5f00\u59cb\u641c\u7d22${target}`);
    waitingTargetRef.current = false;

    await updateSettings(session.session_id, settingsRef.current.speechRate, settingsRef.current.offlineMode);
    if (token !== runTokenRef.current || !runningRef.current) return;
    startFrameTicker(session.session_id);
    announce(`\u6536\u5230\uff0c\u5f00\u59cb\u641c\u7d22${target}`, true);
  }

  async function startCamera(cameraId: string) {
    const constraints: MediaStreamConstraints = {
      video: cameraId
        ? { deviceId: { exact: cameraId }, width: { ideal: 1280 }, height: { ideal: 720 } }
        : { width: { ideal: 1280 }, height: { ideal: 720 } },
      audio: false,
    };

    const stream = await navigator.mediaDevices.getUserMedia(constraints);
    mirrorXRef.current = true;
    if (videoRef.current) {
      videoRef.current.srcObject = stream;
      await videoRef.current.play();
    }
  }

  function stopCamera() {
    const stream = videoRef.current?.srcObject as MediaStream | null;
    stream?.getTracks().forEach((track) => track.stop());
    if (videoRef.current) videoRef.current.srcObject = null;
  }

  function startFrameTicker(sid: string) {
    stopFrameTicker();

    frameTickerRef.current = window.setInterval(async () => {
      if (!runningRef.current || sid !== sessionIdRef.current) return;
      if (!videoRef.current || !videoRef.current.videoWidth || !videoRef.current.videoHeight) return;
      if (frameInFlightRef.current) return;

      try {
        frameInFlightRef.current = true;
        const token = runTokenRef.current;
        const frame = captureFrameBase64(videoRef.current);
        if (!frame) return;

        const mirrorForGuidance = mirrorXRef.current !== settingsRef.current.directionFlip;
        const result = await sendFrame(sid, frame.width, frame.height, frame.imageB64, mirrorForGuidance);
        if (token !== runTokenRef.current || !runningRef.current || sid !== sessionIdRef.current) return;
        setState(result.state);

        const prevInstruction = instructionRef.current;
        const nextInstruction = result.instruction;
        const now = Date.now();
        const changed = nextInstruction && normalize(nextInstruction) !== normalize(prevInstruction);
        const allowChange = now - lastInstructionChangeAtRef.current >= 280;
        if (changed && allowChange) {
          setInstruction(nextInstruction);
          lastInstructionChangeAtRef.current = now;
          const prevDetect = detectPresenceState(prevInstruction);
          const nextDetect = detectPresenceState(nextInstruction);
          const urgent =
            result.state === "done" ||
            /已拿到|任务完成|未检测到/.test(nextInstruction);
          const forceInterrupt =
            urgent ||
            prevDetect !== "unknown" &&
            nextDetect !== "unknown" &&
            prevDetect !== nextDetect;
          announce(nextInstruction, forceInterrupt, urgent);
        }
        if (!changed && nextInstruction) {
          setInstruction(nextInstruction);
        }

        if (result.state === "done") {
          const doneTarget = targetInput || "目标物品";
          const doneText = `已拿到${doneTarget}，任务完成。请说下一个要找的物品。`;
          setStatus("\u4efb\u52a1\u5b8c\u6210");
          setInstruction(doneText);
          announce(doneText, true);
          runningRef.current = false;
          waitingTargetRef.current = false;
          stopFrameTicker();

          // Keep idle voice control active after completion.
          setupRecognition("continuous", true);
        }
      } catch {
        // keep running
      } finally {
        frameInFlightRef.current = false;
      }
    }, 160);
  }

  function captureFrameBase64(video: HTMLVideoElement): CapturedFrame | null {
    const sourceW = video.videoWidth;
    const sourceH = video.videoHeight;
    if (!sourceW || !sourceH) return null;

    const maxW = 640;
    const ratio = sourceW > maxW ? maxW / sourceW : 1;
    const targetW = Math.max(160, Math.round(sourceW * ratio));
    const targetH = Math.max(90, Math.round(sourceH * ratio));

    const canvas = captureCanvasRef.current ?? document.createElement("canvas");
    captureCanvasRef.current = canvas;
    canvas.width = targetW;
    canvas.height = targetH;

    const ctx = canvas.getContext("2d", { alpha: false });
    if (!ctx) return null;

    ctx.drawImage(video, 0, 0, targetW, targetH);
    return {
      imageB64: canvas.toDataURL("image/jpeg", 0.7),
      width: targetW,
      height: targetH,
    };
  }

  function stopFrameTicker() {
    frameInFlightRef.current = false;
    if (frameTickerRef.current) {
      window.clearInterval(frameTickerRef.current);
      frameTickerRef.current = null;
    }
  }

  function restartRecognitionForMode() {
    if (restartTimerRef.current) {
      window.clearTimeout(restartTimerRef.current);
      restartTimerRef.current = null;
    }
    recognitionRef.current?.stop?.();
    recognitionActiveRef.current = false;
    setupRecognition(inputModeRef.current, inputModeRef.current === "continuous");
  }

  function setupRecognition(mode: InputMode, startImmediately: boolean) {
    if (!speechEnabledRef.current) return;

    const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!Recognition) {
      setStatus("\u6d4f\u89c8\u5668\u4e0d\u652f\u6301\u8bed\u97f3\u8bc6\u522b");
      announce("\u5f53\u524d\u6d4f\u89c8\u5668\u4e0d\u652f\u6301\u8bed\u97f3\u8bc6\u522b", true);
      return;
    }

    const rec = new Recognition();
    rec.lang = "zh-CN";
    rec.continuous = mode === "continuous";
    rec.interimResults = false;

    rec.onstart = () => {
      recognitionActiveRef.current = true;
      lastRecognitionStartAtRef.current = Date.now();
      setListening(true);
      setRecognizerState("listening");
    };
    rec.onend = () => {
      recognitionActiveRef.current = false;
      setListening(false);
      setRecognizerState("idle");
      if (speechEnabledRef.current && inputModeRef.current === "continuous") {
        if (restartTimerRef.current) {
          window.clearTimeout(restartTimerRef.current);
        }

        const elapsed = Date.now() - lastRecognitionStartAtRef.current;
        const delay = elapsed < 600 ? 450 : 120;
        restartTimerRef.current = window.setTimeout(() => {
          if (!speechEnabledRef.current || inputModeRef.current !== "continuous") return;
          if (recognitionActiveRef.current) return;
          try {
            rec.start();
          } catch {
            // noop
          }
        }, delay);
      }
    };

    rec.onerror = () => {
      setRecognizerState("error");
    };

    rec.onresult = async (event: any) => {
      const transcript = event?.results?.[event.results.length - 1]?.[0]?.transcript?.trim?.() ?? "";
      if (!transcript) return;

      if (shouldIgnoreTranscript(transcript)) return;

      const control = parseControlCommand(transcript);
      if (control === "stop") {
        stopAll();
        return;
      }

      if (control === "start" && !runningRef.current) {
        setInputMode("continuous");
        inputModeRef.current = "continuous";
        await startAll();
        return;
      }

      setStatus(`\u542c\u5230: ${transcript}`);

      try {
        if (!runningRef.current) {
          const idleTarget = parseTarget(transcript);
          if (!idleTarget) return;
          setInputMode("continuous");
          inputModeRef.current = "continuous";
          await startAll();
          await startTaskForTarget(idleTarget, runTokenRef.current);
          return;
        }

        if (waitingTargetRef.current) {
          const target = parseTarget(transcript);
          if (!target) {
            setInstruction("\u8bf7\u8bf4\u51fa\u4f60\u8981\u627e\u7684\u7269\u54c1\uff0c\u4f8b\u5982\uff1a\u5e2e\u6211\u627e\u676f\u5b50");
            announce("\u6211\u6ca1\u542c\u6e05\uff0c\u8bf7\u518d\u8bf4\u4e00\u6b21\u4f60\u8981\u627e\u7684\u7269\u54c1", true);
            return;
          }
          await startTaskForTarget(target, runTokenRef.current);
          return;
        }

        const sid = sessionIdRef.current;
        if (!sid) return;

        const voice = await sendVoiceCommand(sid, transcript, settingsRef.current.offlineMode);
        if (!runningRef.current) return;
        if (voice.target_label) {
          await startTaskForTarget(voice.target_label, runTokenRef.current);
          return;
        }

        setInstruction(voice.feedback);
        announce(voice.feedback, true);

        if (voice.intent === "complete") {
          const doneTarget = targetInput || voice.target_label || "目标物品";
          const doneText = `已拿到${doneTarget}，任务完成。请说下一个要找的物品。`;
          setState("done");
          setStatus("\u4efb\u52a1\u5b8c\u6210");
          setInstruction(doneText);
          announce(doneText, true);
          stopFrameTicker();
          runningRef.current = false;
          waitingTargetRef.current = false;
          setupRecognition("continuous", true);
        }

        if (voice.should_interrupt) stopAll();
      } catch {
        announce("\u8bed\u97f3\u670d\u52a1\u6682\u65f6\u4e0d\u53ef\u7528", true);
      }
    };

    recognitionRef.current = rec;

    if (startImmediately) {
      if (recognitionActiveRef.current) return;
      try {
        rec.start();
      } catch (error) {
        setStatus(`语音识别启动失败: ${(error as Error).message}`);
        setRecognizerState("error");
      }
    }
  }

  async function startFromButton() {
    speechEnabledRef.current = true;
    if (restartTimerRef.current) {
      window.clearTimeout(restartTimerRef.current);
      restartTimerRef.current = null;
    }
    if (recognitionRef.current) {
      try {
        recognitionRef.current.stop?.();
      } catch {
        // noop
      }
      recognitionRef.current = null;
      recognitionActiveRef.current = false;
    }
    await startAll();
  }

  function startPttListening() {
    speechEnabledRef.current = true;
    if (restartTimerRef.current) {
      window.clearTimeout(restartTimerRef.current);
      restartTimerRef.current = null;
    }
    if (inputModeRef.current !== "ptt") {
      skipModeEffectRef.current = true;
      setInputMode("ptt");
      inputModeRef.current = "ptt";
    }
    if (recognitionRef.current) {
      try {
        recognitionRef.current.stop?.();
      } catch {
        // noop
      }
      recognitionRef.current = null;
      recognitionActiveRef.current = false;
    }

    setupRecognition("ptt", false);

    try {
      recognitionRef.current?.start?.();
    } catch (error) {
      const message = (error as Error).message || "语音识别启动失败";
      if (!message.includes("recognition has already started")) {
        setStatus(`语音识别启动失败: ${message}`);
      }
    }
  }

  function stopPttListening() {
    recognitionRef.current?.stop?.();
  }

  function parseControlCommand(transcript: string): "start" | "stop" | null {
    const normalized = normalize(transcript);
    if (!normalized) return null;

    const isStop =
      normalized.includes("停止") ||
      normalized.includes("结束") ||
      normalized.includes("退出") ||
      normalized.includes("停下") ||
      normalized.includes("stop") ||
      normalized.includes("quit") ||
      normalized.includes("exit");

    if (isStop) return "stop";

    const isStart =
      normalized.includes("开始") ||
      normalized.includes("启动") ||
      normalized.includes("开始引导") ||
      normalized.includes("start");

    if (isStart) return "start";
    return null;
  }

  function parseTarget(transcript: string): string | null {
    const match = transcript.match(CN_FIND);
    const target = match?.groups?.target?.trim();
    if (target) return target;

    const m2 = transcript.match(/find\s+([a-zA-Z0-9_-]+)/i);
    if (m2?.[1]) return m2[1].trim();

    const normalized = transcript
      .replace(/[\s，。！？,.!?：:；;“”"']/g, "")
      .replace(/(请|帮我|我想|我要|一下|麻烦你)/g, "")
      .trim();

    return normalized && normalized.length <= 10 ? normalized : null;
  }

  function shouldIgnoreTranscript(transcript: string): boolean {
    const normalized = normalize(transcript);
    if (!normalized) return true;

    if (inputModeRef.current === "continuous" && speakingRef.current) return true;

    if (inputModeRef.current === "continuous" && Date.now() < ttsTailIgnoreUntilRef.current) return true;

    const now = Date.now();

    recentAnnouncementsRef.current = recentAnnouncementsRef.current.filter((it) => now - it.ts < 8000);

    return recentAnnouncementsRef.current.some((it) => {
      const said = normalize(it.text);
      return said.length > 0 && normalized.includes(said);
    });
  }

  function normalize(text: string): string {
    return text.toLowerCase().replace(/[\s，。！？,.!?：:；;“”"']/g, "");
  }

  function detectPresenceState(text: string): "not_found" | "found" | "unknown" {
    const n = normalize(text || "");
    if (!n) return "unknown";
    if (n.includes("未检测到") || n.includes("没检测到")) return "not_found";
    if (n.includes("在左") || n.includes("在右") || n.includes("正前方") || n.includes("请向") || n.includes("方向对准")) {
      return "found";
    }
    return "unknown";
  }

  function announce(text: string, force: boolean, bypassRateLimit = false) {
    if (!text || !("speechSynthesis" in window)) return;

    const normalized = normalize(text);
    if (!normalized) return;

    if (!force && normalized === lastAnnouncedRef.current) return;
    const now = Date.now();
    if (!force && !bypassRateLimit && now - lastSpeakAtRef.current < 650) return;

    // In normal guidance mode, do not interrupt the current sentence.
    if (!force && speakingRef.current) {
      pendingAnnouncementRef.current = text;
      return;
    }

    if (force) {
      pendingAnnouncementRef.current = null;
    }

    const utter = new SpeechSynthesisUtterance(text);
    utter.lang = "zh-CN";
    utter.rate = RATE_MAP[settingsRef.current.speechRate] ?? 1;

    if (voicesReadyRef.current) {
      const voices = window.speechSynthesis.getVoices();
      const zhVoice = voices.find((v) => v.lang.toLowerCase().startsWith("zh"));
      if (zhVoice) utter.voice = zhVoice;
    }

    utter.onstart = () => {
      speakingRef.current = true;
    };
    utter.onend = () => {
      speakingRef.current = false;
      ttsTailIgnoreUntilRef.current = Date.now() + 900;
      const pending = pendingAnnouncementRef.current;
      if (pending) {
        pendingAnnouncementRef.current = null;
        window.setTimeout(() => announce(pending, false, true), 40);
      }
    };
    utter.onerror = () => {
      speakingRef.current = false;
      ttsTailIgnoreUntilRef.current = Date.now() + 700;
    };

    // Only hard-interrupt when explicitly requested (e.g., stop/done).
    if (force) {
      try {
        window.speechSynthesis.cancel();
      } catch {
        // noop
      }
    }

    window.speechSynthesis.speak(utter);
    lastAnnouncedRef.current = normalized;
    lastSpeakAtRef.current = now;
    recentAnnouncementsRef.current.push({ text, ts: now });
  }

  return (
    <main style={{ minHeight: "100vh", padding: 16 }}>
      <section style={{ maxWidth: 1080, margin: "0 auto", display: "grid", gap: 12 }}>
        <header className="card" style={{ padding: 14, display: "flex", gap: 10, flexWrap: "wrap" }}>
          <div style={{ flex: 1, minWidth: 220, padding: 12, color: "#415365", fontWeight: 700 }}>
            当前目标：{targetInput || "等待语音设置目标"}
          </div>
          <button className="cta" onClick={startFromButton} aria-label="开始引导">开始</button>
          <button className="danger" onClick={stopAll} aria-label="停止引导">停止</button>
          <button onClick={resetAll} aria-label="重置任务">重置</button>
          <button onClick={() => announce(instructionRef.current, true)} aria-label="测试语音">测试语音</button>

          <select
            aria-label="语音输入模式"
            value={inputMode}
            onChange={(e) => setInputMode(e.target.value as InputMode)}
            style={{ padding: 10, borderRadius: 12 }}
          >
            <option value="ptt">PTT 按住说话</option>
            <option value="continuous">连续监听</option>
          </select>

          <button
            aria-label="按住说话"
            onPointerDown={startPttListening}
            onPointerUp={stopPttListening}
            onPointerCancel={stopPttListening}
            onPointerLeave={stopPttListening}
            style={{ background: "#1f6feb", color: "#fff" }}
          >
            按住说话
          </button>

          <Link href="/settings" style={{ textDecoration: "none" }}>
            <button aria-label="打开设置">设置</button>
          </Link>
          <Link href="/" style={{ textDecoration: "none" }}>
            <button aria-label="回首页">首页</button>
          </Link>
        </header>

        <div className="card" style={{ overflow: "hidden", position: "relative", background: "#000" }}>
          <video
            ref={videoRef}
            aria-label="摄像头画面"
            muted
            playsInline
            style={{ width: "100%", aspectRatio: "16 / 9", objectFit: "cover", display: "block" }}
          />
          <div
            style={{
              position: "absolute",
              left: 14,
              bottom: 12,
              background: "rgba(0,0,0,0.55)",
              color: "#fff",
              padding: "8px 10px",
              borderRadius: 10,
              fontSize: 14,
            }}
          >
            {listening ? "正在监听用户语音" : "未监听"}
          </div>
        </div>

        <section className="card" aria-live="assertive" style={{ padding: 18 }}>
          <p style={{ margin: "0 0 8px", color: "#415365" }}>状态：{status}</p>
          <p style={{ margin: "0 0 8px", color: "#415365" }}>阶段：{state}</p>
          <p style={{ margin: "0 0 8px", color: "#415365" }}>语音能力：{ttsSupported ? "可用" : "不可用"}</p>
          <p style={{ margin: 0, fontSize: 28, fontWeight: 800 }}>系统：{instruction}</p>
        </section>
      </section>
    </main>
  );
}