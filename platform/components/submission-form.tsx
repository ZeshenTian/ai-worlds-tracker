"use client";

import { useState, type FormEvent } from "react";
import { CheckCircle2, Send } from "lucide-react";
import { themes } from "@/lib/worlds";

export function SubmissionForm() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [fields, setFields] = useState<Record<string,string[]>>({});
  const [receipt, setReceipt] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const data = Object.fromEntries(new FormData(event.currentTarget));
    setBusy(true);
    setError("");
    setFields({});
    try {
      const response = await fetch("/api/submissions", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data),
      });
      const result = await response.json() as { id?: string; error?: string; fields?: Record<string,string[]> };
      if (!response.ok) {
        setError(result.error || "暂时无法完成投稿，请重试。");
        setFields(result.fields || {});
        return;
      }
      if (!result.id) throw new Error("Missing receipt");
      setReceipt(result.id);
    } catch {
      setError("网络连接中断，请稍后再试。");
    } finally {
      setBusy(false);
    }
  }
  if (receipt) return (
    <section className="panel form-success" tabIndex={-1} ref={element => element?.focus()}>
      <CheckCircle2 size={30} /><h2>投稿已收到</h2>
      <p>案例已进入待审核队列。</p><p className="receipt">投稿编号 <code>{receipt}</code></p>
      <button type="button" className="button" onClick={() => setReceipt("")}>继续投稿</button>
    </section>
  );

  const errors = (name: string) => fields[name] && <span className="field-error" id={`${name}-error`}>{fields[name][0]}</span>;
  const props = (name: string) => ({
    id: name, name, "aria-invalid": Boolean(fields[name]),
    "aria-describedby": fields[name] ? `${name}-error` : undefined,
  });
  return (
    <form className="panel submission-form" onSubmit={submit}>
      <div className="form-row">
        <label htmlFor="title">案例名称 <span aria-hidden="true">*</span><input {...props("title")} required minLength={2} maxLength={120} placeholder="例如 Papertrails" />{errors("title")}</label>
        <label htmlFor="theme">世界主题 <span aria-hidden="true">*</span><select {...props("theme")} required defaultValue=""><option value="">选择主题</option>{Object.entries(themes).map(([key,label]) => <option key={key} value={key}>{label}</option>)}</select>{errors("theme")}</label>
      </div>
      <label htmlFor="source">作者原帖或项目介绍 <span aria-hidden="true">*</span><input {...props("source")} required type="url" maxLength={800} placeholder="https://…" />{errors("source")}</label>
      <div className="form-row">
        <label htmlFor="demo">试玩链接 <small>选填</small><input {...props("demo")} type="url" maxLength={800} placeholder="https://…" />{errors("demo")}</label>
        <label htmlFor="repo">源码链接 <small>选填</small><input {...props("repo")} type="url" maxLength={800} placeholder="https://…" />{errors("repo")}</label>
      </div>
      <label htmlFor="notes">模型与工作流 <small>选填</small><textarea {...props("notes")} maxLength={1500} rows={5} placeholder="使用了哪些模型或工具？有公开的提示词、费用或耗时吗？" />{errors("notes")}</label>
      <div className="honeypot" aria-hidden="true"><label htmlFor="website">网站<input id="website" name="website" tabIndex={-1} autoComplete="off" /></label></div>
      {error && <p role="alert" className="form-error">{error}</p>}
      <button className="button button-primary" type="submit" disabled={busy}><Send size={17} />{busy ? "正在提交…" : "提交审核"}</button>
    </form>
  );
}
