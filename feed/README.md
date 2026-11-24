# WorldFeed

WorldFeed 是同仓库独立构建的静态站。它从 `data/exports/ai_worlds.json` 生成世界流，使用工作台现有的翻译和封面，收藏、已看记录和语言偏好均保存在浏览器中。

## 本地运行

使用 Node.js 22.13 或更高版本，在 `feed/` 中运行以下命令。

```sh
npm ci --include=dev
npm run build
npm run preview
```

`npm run build` 会验证固定版本的镜像文件与许可证，生成世界列表、同步封面、运行 TypeScript 类型检查并输出 `dist/`。开发时用 `npm run dev` 启动 Vite。

## 更新数据与镜像

- 运行 `npm run probe` 探测新增地址并重试网络错误。运行 `npm run probe -- --refresh` 可重查所有可用试玩地址。缓存位于 `../data/state/embed_probe.json`。部署域名确定后可设置 `FEED_ORIGIN`，使白名单式 `frame-ancestors` 按实际父页面来源判定。
- `scripts/mirrors.config.json` 记录许可、上游 commit、源文件和 SHA-256。`vendor/` 保存同一版本的原文件，常规构建可以离线完成。运行 `npm run mirrors -- --refresh` 会从相同 commit 重新下载并验证文件。作品及第三方许可证随镜像一起提供。
- `npm run data` 合并数据、探测结果和镜像清单。英文优先复用上游与工作台译文。`content/english.json` 补充当前快照缺失的内容。英文抽屉保留可直接展示的原文引语，其他语种可通过原文链接查看。
- 推荐流按镜像、已验证的嵌入、带预览的嵌入和外链预览排序。对于只有原帖的案例，按钮指向原作。文本案例可以从直链进入。

## Chrome 验收

安装 Google Chrome 后，在构建完成的 `feed/` 中运行 `npm run verify`。脚本自行启动临时静态服务，在独立的真实 Chrome 窗口测试桌面与移动视口，随后关闭窗口与服务。跨域试玩和原站跳转需要联网。如 Chrome 需要代理，可设置 `FEED_CHROME_PROXY`。默认用 Francis Turbine Explorer 验证跨域画布，可用 `FEED_VERIFY_EMBED` 指定当前快照中另一个有真实画布的可嵌入作品。

截图、Chrome 版本、实际测试的世界和错误计数保存在 `acceptance/`。嵌入分级依据 HTTP 响应头与登录墙探测，真实 Chrome 验收覆盖清单里列出的作品。

## 独立部署

- **Vercel** 选择此仓库，Root Directory 设为 `feed`，允许构建读取根目录外的共享文件，构建命令为 `npm run build`，输出目录为 `dist`。
- **Cloudflare Pages** 新建独立的 Pages 项目，在 GitHub 配置仓库变量 `CLOUDFLARE_FEED_PAGES_PROJECT` 和 Secrets `CLOUDFLARE_ACCOUNT_ID`、`CLOUDFLARE_API_TOKEN`。手动运行 `Deploy WorldFeed to Cloudflare Pages` 即可发布 `feed/dist`。
