import { Shell } from "@/components/atlas-shell";

export default function NotFound() {
  return <Shell active="catalog"><div className="container subpage empty-state"><h1>没有找到这个案例</h1><p>链接可能已变更。可以从世界目录重新查找。</p><a className="button button-primary" href="/#catalog">查看世界目录</a></div></Shell>;
}
