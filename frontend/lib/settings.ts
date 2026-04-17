import { AppSettings } from "@/types/api";

const KEY = "vision-assist-settings";

export const defaultSettings: AppSettings = {
  speechRate: "medium",
  offlineMode: false,
  cameraId: "",
  directionFlip: false,
};

export function loadSettings(): AppSettings {
  if (typeof window === "undefined") {
    return defaultSettings;
  }

  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return defaultSettings;
    return { ...defaultSettings, ...(JSON.parse(raw) as Partial<AppSettings>) };
  } catch {
    return defaultSettings;
  }
}

export function saveSettings(settings: AppSettings): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(KEY, JSON.stringify(settings));
}
