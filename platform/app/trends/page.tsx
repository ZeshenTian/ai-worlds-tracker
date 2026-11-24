import type { Metadata } from "next";
import { Shell } from "@/components/atlas-shell";
import { TrendsView } from "@/components/trends-view";

export const metadata: Metadata = { title: "趋势与工作流" };

export default function Trends() {
  return (
    <Shell active="trends">
      <TrendsView />
    </Shell>
  );
}
