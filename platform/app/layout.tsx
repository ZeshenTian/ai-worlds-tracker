import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "生成世界图鉴", template: "%s · 生成世界图鉴" },
  description: "探索 AI 生成的交互世界。试玩项目、阅读创作流程、比较模型与技术栈。",
  icons: { icon: "/atlas-icon.png" },
};

export const viewport: Viewport = {
  themeColor: "#ffffff",
  colorScheme: "light",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
