import type { Metadata, Viewport } from "next";
import "./globals.css";

const atlasUrl = "https://generated-worlds-atlas.zeshentian1.chatgpt.site";
const title = "生成世界图鉴";
const description = "按模型、主题和技术栈探索 AI 创作的世界，直接试玩或查看作者的演示。";
const image = { url: atlasUrl + "/share/atlas-preview.jpg", width: 1200, height: 630, alt: "生成世界图鉴首页的筛选栏和四个可试玩世界" };

export const metadata: Metadata = {
  title: { default: title, template: "%s · 生成世界图鉴" },
  description,
  openGraph: { type: "website", url: atlasUrl + "/", title, description, images: [image] },
  twitter: { card: "summary_large_image", title, description, images: [image] },
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
