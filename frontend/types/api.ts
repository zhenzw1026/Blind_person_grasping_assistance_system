export type GuideState =
  | "searching"
  | "target_locked"
  | "approaching"
  | "near_field"
  | "grasp_guide"
  | "done";

export interface BoundingBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface DetectionItem {
  label: string;
  confidence: number;
  box: BoundingBox;
}

export interface SessionResponse {
  session_id: string;
  target_label: string;
  state: GuideState;
  current_instruction: string;
}

export interface VisionFrameResponse {
  state: GuideState;
  instruction: string;
  confidence: number;
  target_found: boolean;
  distance_hint: "far" | "mid" | "near" | null;
  target_box: BoundingBox | null;
  hand_box: BoundingBox | null;
  detection_items: DetectionItem[];
  debug: Record<string, string | number | boolean | null> | null;
}

export interface VoiceCommandResponse {
  intent: string;
  target_label?: string;
  should_interrupt: boolean;
  feedback: string;
}

export type SpeechRate = "slow" | "medium" | "fast";

export interface AppSettings {
  speechRate: SpeechRate;
  offlineMode: boolean;
  cameraId: string;
  directionFlip: boolean;
}
