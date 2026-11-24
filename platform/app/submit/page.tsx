import type { Metadata } from "next";
import { FileQuestion, Globe2, ListChecks } from "lucide-react";
import { Shell } from "@/components/atlas-shell";
import { SubmissionForm } from "@/components/submission-form";

export const metadata: Metadata = { title: "投稿案例" };

export default function Submit() {
  return (
    <Shell active="submit">
      <div className="container subpage">
        <header className="page-heading"><h1>投稿案例</h1><p>推荐你制作或发现的 AI 交互世界，附上创作者的原帖或项目介绍。</p></header>
        <div className="submit-grid">
          <SubmissionForm />
          <aside className="panel submit-help">
            <h2>收录条件</h2>
            <ul>
              <li><Globe2 size={19} /><span>项目提供可探索、操控或交互的场景。</span></li>
              <li><FileQuestion size={19} /><span>作者公开说明了 AI 模型参与创作的方式。</span></li>
              <li><ListChecks size={19} /><span>提供可追溯的来源。若有试玩、源码或提示词，可一并补充。</span></li>
            </ul>
            <p>投稿会进入审核队列。请只填写公开项目资料，避免在补充说明中留下个人联系方式。</p>
          </aside>
        </div>
      </div>
    </Shell>
  );
}
