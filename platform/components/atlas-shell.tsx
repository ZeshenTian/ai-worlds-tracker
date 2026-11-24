import { submissionUrl } from "@/lib/worlds";
import { Aperture, Plus } from "lucide-react";
import type { ReactNode } from "react";

export function Header({ active }: { active: "catalog" | "trends" | "submit" }) {
  return (
    <header className="site-header">
      <div className="container nav-inner">
        <a className="brand" href="/" aria-label="生成世界图鉴首页">
          <span className="brand-icon"><Aperture size={20} strokeWidth={1.7} /></span>
          <span>生成世界图鉴</span>
        </a>
        <nav aria-label="主导航" className="primary-nav">
          <a href="/" aria-current={active === "catalog" ? "page" : undefined}>世界目录</a>
          <a href="/trends" aria-current={active === "trends" ? "page" : undefined}>趋势与工作流</a>
        </nav>
        <a className="button nav-submit" href={submissionUrl} target="_blank" rel="noopener noreferrer" aria-current={active === "submit" ? "page" : undefined}>
          <Plus size={16} strokeWidth={2.2} /> <span>提交新世界</span>
        </a>
      </div>
    </header>
  );
}

export function Footer() {
  return (
    <footer className="site-footer">
      <div className="container footer-inner">
        <a className="brand" href="/"><Aperture size={18} /><span>生成世界图鉴</span></a>
        <span>基于公开原帖与作者发布的项目</span>
        <a href="/trends#method">统计口径</a>
      </div>
    </footer>
  );
}

export function Shell({ active, children }: { active: "catalog" | "trends" | "submit", children: ReactNode }) {
  return <><a href="#main" className="skip-link">跳到正文</a><Header active={active} /><main id="main">{children}</main><Footer /></>;
}
