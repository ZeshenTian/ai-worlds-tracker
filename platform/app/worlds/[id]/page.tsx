import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { Shell } from "@/components/atlas-shell";
import { WorldDetailView } from "@/components/world-detail-view";
import { worlds } from "@/lib/worlds";

type Props = { params: Promise<{ id: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { id } = await params;
  const world = worlds.find((item) => item.world_id === id);
  return world ? { title: world.title, description: world.summary } : { title: "Not Found" };
}

export default async function WorldPage({ params }: Props) {
  const { id } = await params;
  const world = worlds.find((item) => item.world_id === id);
  if (!world) notFound();

  const similar = worlds
    .filter((item) => world.theme_category !== "other" && item.world_id !== id && item.theme_category === world.theme_category)
    .slice(0, 3);

  return (
    <Shell active="catalog">
      <WorldDetailView world={world} similar={similar} />
    </Shell>
  );
}
