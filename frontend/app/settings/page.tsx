"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AppSettings, SpeechRate } from "@/types/api";
import { defaultSettings, loadSettings, saveSettings } from "@/lib/settings";

export default function SettingsPage() {
  const [settings, setSettings] = useState<AppSettings>(defaultSettings);
  const [cameras, setCameras] = useState<MediaDeviceInfo[]>([]);

  useEffect(() => {
    setSettings(loadSettings());

    navigator.mediaDevices
      .enumerateDevices()
      .then((devices) => setCameras(devices.filter((d) => d.kind === "videoinput")))
      .catch(() => setCameras([]));
  }, []);

  function update(next: Partial<AppSettings>) {
    const merged = { ...settings, ...next };
    setSettings(merged);
    saveSettings(merged);
  }

  return (
    <main style={{ padding: 24, display: "grid", placeItems: "center" }}>
      <section className="card" style={{ width: "min(720px, 100%)", padding: 24 }}>
        <h1 style={{ marginTop: 0 }}>设置</h1>

        <label style={{ display: "block", marginBottom: 14 }}>
          语音速度
          <select
            value={settings.speechRate}
            onChange={(e) => update({ speechRate: e.target.value as SpeechRate })}
            style={{ marginTop: 8, width: "100%", padding: 10, borderRadius: 12 }}
          >
            <option value="slow">慢</option>
            <option value="medium">中</option>
            <option value="fast">快</option>
          </select>
        </label>

        <label style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 14 }}>
          <input
            type="checkbox"
            checked={settings.offlineMode}
            onChange={(e) => update({ offlineMode: e.target.checked })}
          />
          开启离线模式（Whisper 限制模式）
        </label>

        <label style={{ display: "block", marginBottom: 14 }}>
          摄像头选择
          <select
            value={settings.cameraId}
            onChange={(e) => update({ cameraId: e.target.value })}
            style={{ marginTop: 8, width: "100%", padding: 10, borderRadius: 12 }}
          >
            <option value="">系统默认摄像头</option>
            {cameras.map((cam) => (
              <option key={cam.deviceId} value={cam.deviceId}>
                {cam.label || `Camera ${cam.deviceId.slice(0, 6)}`}
              </option>
            ))}
          </select>
        </label>

        <label style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 14 }}>
          <input
            type="checkbox"
            checked={settings.directionFlip}
            onChange={(e) => update({ directionFlip: e.target.checked })}
          />
          方位左右校准反转（如果播报左右反了就开启）
        </label>

        <div style={{ display: "flex", gap: 12, marginTop: 20 }}>
          <Link href="/assist" style={{ textDecoration: "none" }}>
            <button className="cta">返回主界面</button>
          </Link>
          <Link href="/" style={{ textDecoration: "none" }}>
            <button>回首页</button>
          </Link>
        </div>
      </section>
    </main>
  );
}
