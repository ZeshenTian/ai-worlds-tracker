import { Boxes, ChartNoAxesColumnIncreasing, Layers3, Play } from "lucide-react";
import { Shell } from "@/components/atlas-shell";
import { WorldCatalog } from "@/components/world-catalog";
import meta from "@/data/meta.json";
import { UpdateTime } from "@/components/update-time";
import { count } from "@/lib/worlds";

export default function Home() {
  return (
    <Shell active="catalog">
      <section className="hero-wrap">
        <div className="container">
          <div className="hero">
            <div className="hero-content">
              <div className="hero-kicker"><span /> AI INTERACTIVE WORLD ATLAS</div>
              <h1>进入由 AI 构建的<br /><em>交互世界</em></h1>
              <p>从纸雕山谷到程序化星球，试玩由 AI 构建的世界，<br className="desktop-break" />并了解创作者如何把想法变成可探索的场景。</p>
              <div className="hero-actions">
                <a className="button button-primary" href="#catalog"><Play size={17} fill="currentColor" />探索案例</a>
                <a className="button button-glass" href="/trends"><ChartNoAxesColumnIncreasing size={17} />查看趋势</a>
              </div>
            </div>
            <span className="hero-credit">概念插图</span>
          </div>
          <div className="stats-band" aria-label="目录统计">
            <div><Boxes size={20} /><strong>{count.all}</strong><span>收录案例</span></div>
            <div><Play size={19} /><strong>{count.playable}</strong><span>已验证可试玩</span></div>
            <div><Layers3 size={20} /><strong>{count.open}</strong><span>确认开源</span></div>
            <div className="sync-time"><UpdateTime iso={meta.last_updated_at} /><span>最近更新</span></div>
          </div>
        </div>
      </section>
      <WorldCatalog />
    </Shell>
  );
}
