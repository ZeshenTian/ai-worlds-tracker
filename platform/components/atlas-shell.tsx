/* eslint-disable @next/next/no-html-link-for-pages */
import { Aperture, Plus } from "lucide-react";
import type { ReactNode } from "react";
import { count, submissionUrl } from "@/lib/worlds";
import { CommandSearch } from "./command-search";

export function Header({
  active,
  isHome = false,
}: {
  active: "catalog" | "trends" | "submit";
  isHome?: boolean;
}) {
  return (
    <header className="wb-topbar">
      <div className={isHome ? "wb-topbar-inner wb-topbar-full" : "wb-topbar-inner container"}>
        <div className="wb-brand-group">
          <a className="brand" href="/" aria-label="生成世界图鉴首页">
            <span className="brand-icon" aria-hidden="true">
              <Aperture size={17} strokeWidth={1.9} />
            </span>
            <span className="brand-name">生成世界图鉴</span>
          </a>
          <span className="brand-count">{count.all} 案例</span>
        </div>

        <CommandSearch isHome={isHome} />

        <div className="wb-nav-group">
          <nav aria-label="主导航" className="primary-nav">
            <a href="/" aria-current={active === "catalog" ? "page" : undefined}>
              世界目录
            </a>
            <a href="/trends" aria-current={active === "trends" ? "page" : undefined}>
              趋势与工作流
            </a>
          </nav>
          <a
            className="button button-primary nav-submit"
            href={submissionUrl}
            target="_blank"
            rel="noopener noreferrer"
            aria-current={active === "submit" ? "page" : undefined}
          >
            <Plus size={15} strokeWidth={2.2} />
            <span>提交新世界</span>
          </a>
        </div>
      </div>
    </header>
  );
}

export function Footer() {
  return (
    <footer className="site-footer">
      <div className="container footer-inner">
        <a className="brand" href="/">
          <Aperture size={16} />
          <span>生成世界图鉴</span>
        </a>
        <span>基于公开原帖与作者发布的项目 · 纯静态离线可检索</span>
        <a href="/trends#method" className="text-link">
          统计口径
        </a>
      </div>
    </footer>
  );
}

export function Shell({
  active,
  isHome = false,
  hideFooter = false,
  children,
}: {
  active: "catalog" | "trends" | "submit";
  isHome?: boolean;
  hideFooter?: boolean;
  children: ReactNode;
}) {
  return (
    <>
      <a href="#main" className="skip-link">
        跳到正文
      </a>
      <Header active={active} isHome={isHome} />
      <main id="main" className={isHome ? "wb-page-main" : undefined}>
        {children}
      </main>
      {!hideFooter && <Footer />}
    </>
  );
}
