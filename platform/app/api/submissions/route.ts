import { getDb } from "@/db";
import { submissions } from "@/db/schema";
import { referenceKey, submissionSchema } from "@/lib/submissions";
import { worlds } from "@/lib/worlds";

const existing = new Set(worlds.map(world => referenceKey(world.original_post_url)));
const maxBytes = 8192;

async function readPayload(request: Request) {
  if (Number(request.headers.get("content-length")) > maxBytes || !request.body) return undefined;
  const reader = request.body.getReader();
  const decoder = new TextDecoder();
  let length = 0;
  let json = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    length += value.byteLength;
    if (length > maxBytes) {
      await reader.cancel();
      return undefined;
    }
    json += decoder.decode(value, { stream: true });
  }
  return JSON.parse(json + decoder.decode()) as unknown;
}

export async function POST(request: Request) {
  const origin = request.headers.get("origin");
  if (origin && origin !== new URL(request.url).origin) {
    return Response.json({ error: "请从本站提交案例。" }, { status: 403 });
  }
  if (request.headers.get("content-type")?.split(";")[0]?.trim() !== "application/json") {
    return Response.json({ error: "投稿格式无效。" }, { status: 415 });
  }
  let payload: unknown;
  try {
    payload = await readPayload(request);
  } catch {
    return Response.json({ error: "投稿格式无效。" }, { status: 400 });
  }
  if (payload === undefined) return Response.json({ error: "投稿内容过长或为空。" }, { status: 413 });

  const result = submissionSchema.safeParse(payload);
  if (!result.success) return Response.json({ error: "请检查填写内容。", fields: result.error.flatten().fieldErrors }, { status: 400 });
  const { title, source, demo, repo, theme, notes, website } = result.data;
  if (website) return Response.json({ error: "投稿格式无效。" }, { status: 400 });

  const sourceKey = referenceKey(source);
  if (existing.has(sourceKey)) {
    return Response.json({ error: "该原帖对应的案例已收录。" }, { status: 409 });
  }
  try {
    const id = crypto.randomUUID();
    const saved = await getDb().insert(submissions).values({
      id, title, source, sourceKey, demo: demo || null, repo: repo || null,
      theme, notes: notes || null, status: "pending", createdAt: new Date().toISOString(),
    }).onConflictDoNothing({ target: submissions.sourceKey }).returning({ id: submissions.id });
    if (saved.length === 0) {
      return Response.json({ error: "这条来源链接已有投稿记录。" }, { status: 409 });
    }
    return Response.json({ id, status: "pending" }, { status: 201 });
  } catch (error) {
    console.error("Unable to save atlas submission", error);
    return Response.json({ error: "暂时无法保存投稿。填写内容已保留，请稍后再试。" }, { status: 503 });
  }
}
