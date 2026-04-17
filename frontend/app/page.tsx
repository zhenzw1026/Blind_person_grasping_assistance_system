"use client";

import Link from "next/link";

export default function HomePage() {
  return (
    <main style={{ display: "grid", placeItems: "center", padding: 24 }}>
      <section className="card" style={{ width: "min(680px, 100%)", padding: 36, textAlign: "center" }}>
        <h1 style={{ marginTop: 0, fontSize: "clamp(2rem, 4vw, 2.8rem)" }}>视障辅助系统</h1>
        <p style={{ color: "#415365", fontSize: 18, lineHeight: 1.6 }}>
          通过摄像头和语音交互，帮助你快速找到并拿取目标物体。
        </p>
        <div style={{ display: "flex", gap: 12, justifyContent: "center", flexWrap: "wrap", marginTop: 26 }}>
          <Link href="/assist" aria-label="开始使用" style={{ textDecoration: "none" }}>
            <button className="cta" style={{ minWidth: 180, minHeight: 64, fontSize: 22 }}>开始使用</button>
          </Link>
          <Link href="/settings" aria-label="打开设置" style={{ textDecoration: "none" }}>
            <button style={{ minWidth: 140, minHeight: 64, fontSize: 20 }}>设置</button>
          </Link>
        </div>
        <p style={{ marginTop: 24, fontWeight: 700 }}>当前状态：未启动</p>
      </section>
    </main>
  );
}
