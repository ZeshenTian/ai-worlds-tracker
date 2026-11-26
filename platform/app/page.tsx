import { Shell } from "@/components/atlas-shell";
import { WorldCatalog } from "@/components/world-catalog";

export default function Home() {
  return (
    <Shell active="catalog" isHome hideFooter>
      <WorldCatalog />
    </Shell>
  );
}
