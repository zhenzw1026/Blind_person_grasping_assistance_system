import { SessionResponse, VisionFrameResponse, VoiceCommandResponse } from "@/types/api";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000";

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || "API request failed");
  }

  // Some backend routes intentionally return 204 No Content.
  if (res.status === 204) {
    return undefined as T;
  }

  const text = await res.text();
  if (!text) {
    return undefined as T;
  }

  return JSON.parse(text) as T;
}

export async function startSession(targetLabel: string): Promise<SessionResponse> {
  const res = await fetch(`${API_BASE}/api/session/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ target_label: targetLabel }),
  });
  return handle<SessionResponse>(res);
}

export async function resetSession(sessionId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/session/${sessionId}/reset`, { method: "POST" });
  await handle(res);
}

export async function updateSettings(sessionId: string, speechRate: string, offlineMode: boolean): Promise<void> {
  const res = await fetch(`${API_BASE}/api/session/${sessionId}/settings`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ speech_rate: speechRate, offline_mode: offlineMode }),
  });
  await handle(res);
}

export async function sendFrame(
  sessionId: string,
  frameWidth: number,
  frameHeight: number,
  imageB64: string,
  mirrorX: boolean,
): Promise<VisionFrameResponse> {
  const res = await fetch(`${API_BASE}/api/vision/frame`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_id: sessionId,
      frame_width: frameWidth,
      frame_height: frameHeight,
      mirror_x: mirrorX,
      image_b64: imageB64,
      server_detect: true,
      detect_conf: 0.15,
      detections: [],
    }),
  });
  return handle<VisionFrameResponse>(res);
}

export async function sendVoiceCommand(
  sessionId: string,
  transcript: string,
  offlineMode: boolean,
): Promise<VoiceCommandResponse> {
  const res = await fetch(`${API_BASE}/api/voice/command`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_id: sessionId,
      transcript,
      offline_mode: offlineMode,
    }),
  });
  return handle<VoiceCommandResponse>(res);
}
