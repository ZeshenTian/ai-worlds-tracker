# 生成世界图鉴

第二阶段站点从审核快照读取案例。首发包含 59 条，首页只高亮经浏览器验证的试玩入口。目录支持搜索、组合筛选、排序和卡片或列表布局。每条案例有独立链接，展示作者来源、工作流、模型与成本证据。在线试玩和源码在新标签页打开。

## 运行项目

需要 Node.js 22.13+。在此目录运行以下命令。

```sh
npm ci
npm run build
node --import ./scripts/sites-env.mjs ./node_modules/wrangler/bin/wrangler.js d1 execute DB \
  --local --config dist/server/wrangler.json --persist-to .wrangler/state \
  --file drizzle/0000_silent_lilandra.sql
npm start
```

本地开发可使用 `npm run dev`。仅在未初始化本地数据库时应用建表迁移。Sites 部署时会应用同一份迁移。

## 更新案例

在仓库根目录运行 uv run python -m src.publish_catalog，生成审核后的案例与更新时间快照，再重新构建网站。目录、详情和趋势页共用这份数据。卡片封面来自试玩截图；未取得可用画面的案例显示占位。

## 投稿记录

主导航打开本项目的 GitHub Issue Form，静态部署无需数据库。Sites 保留的旧入口 /submit 通过 `POST /api/submissions` 把记录写入站点 D1。提交成功后返回投稿编号。相同来源链接只保存一条投稿，已收录的原帖链接不能重复投稿。站点管理者可在 Sites 的数据库表视图中查看 `submissions`。条目默认状态为 `pending`，复核后通过第一阶段流程进入正式案例导出。

本地可使用下列命令读取待审核队列。

```sh
node --import ./scripts/sites-env.mjs ./node_modules/wrangler/bin/wrangler.js d1 execute DB \
  --local --config dist/server/wrangler.json --persist-to .wrangler/state \
  --command "SELECT id, title, source, created_at FROM submissions WHERE status = 'pending' ORDER BY created_at DESC"
```

## 静态构建

在本目录执行 npm ci 与 npm run build:static，输出 out/。每条作品有独立 HTML，筛选和搜索在浏览器中运行。/submit 转入仓库投稿表单。仓库根 README 提供 Vercel 和 Cloudflare Pages 部署入口。
