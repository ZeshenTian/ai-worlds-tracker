# WorldFeed

WorldFeed 只展示前沿作品中可镜像或嵌入的世界。进入时直接挂载 iframe，镜像排在首位。方向键和滚轮可在外层页面切换世界。跨域游戏获得焦点后，可点击外侧导航或将指针移至工具栏滚动。

在 Node.js 22.13+ 下运行 `npm ci` 和 `npm run build`，部署输出目录 `dist/`。`VITE_ATLAS_URL` 指向图鉴。镜像的许可证及固定版本记录位于 `scripts/mirrors.config.json` 和各镜像目录。

在本地分别用 8870、8871 端口提供 Atlas 和 WorldFeed 的静态构建，再运行 `npm run verify`。默认由本机共享浏览器工具打开测试标签页。可用 `TEST_ATLAS_URL`、`TEST_FEED_URL` 或 `TEST_BROWSER_HELPER` 覆盖本机路径。

构建还需要 Python 3.9+，用于复用图鉴已有的前沿模型判定规则。世界标题、模型与互动控件集中在 48px 顶栏，桌面可通过问号查看快捷键。
