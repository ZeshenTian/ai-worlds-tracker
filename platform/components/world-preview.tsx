import { Aperture } from "lucide-react";
import type { World } from "@/lib/worlds";

export function WorldPreview({world}: {world: World}) {
  return world.thumbnail_url
    ? <img src={world.thumbnail_url} alt={world.title + " 的试玩画面"} loading="lazy" width="960" height="540" />
    : <span className="cover-placeholder"><Aperture size={32} strokeWidth={1.15} /><span>暂无实景预览</span></span>;
}
