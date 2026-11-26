import type { Metadata, Viewport } from "next";
import "./globals.css";

const atlasUrl = "https://explore.worldfeed.space";
const title = "WorldFeed Explore";
const description = "Explore frontier AI-generated 3D worlds by model, theme, and tech stack. Play live in browser or inspect original demos.";
const image = { url: atlasUrl + "/share/atlas-preview.jpg", width: 1200, height: 630, alt: "WorldFeed Explore catalog with filters and playable AI-generated 3D worlds" };

export const metadata: Metadata = {
  title: { default: title, template: "%s · WorldFeed Explore" },
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
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
