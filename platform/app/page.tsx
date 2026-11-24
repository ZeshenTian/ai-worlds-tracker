import { Shell } from "@/components/atlas-shell";
import { WorldCatalog } from "@/components/world-catalog";
import meta from "@/data/meta.json";

export default function Home() {
  return (
    <Shell active="catalog" isHome hideFooter>
      <WorldCatalog lastUpdatedAt={meta.last_updated_at} />
    </Shell>
  );
}
