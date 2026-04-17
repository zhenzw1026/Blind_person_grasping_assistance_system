import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "视障视觉辅助系统",
  description: "Realtime + Whisper 离线兜底的视障辅助 Web 应用",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
