# 生成世界图鉴

图鉴读取已审核的前沿案例快照，默认显示全部作品，前四个位置优先展示能在 WorldFeed 直接试玩的作品，其余按发布日期排序。可切换到可试玩或视频演示，支持模型、主题、技术栈组合筛选。可站内试玩的作品直达 WorldFeed，卡片保留作者入口、原帖和已披露的源码。

在 Node.js 22.13+ 下运行 `npm ci` 和 `npm run build:static`，部署输出目录 `out/`。通过 `NEXT_PUBLIC_WORLDFEED_URL` 指定 WorldFeed 的公开地址。默认本地体验地址为 Atlas 8870 端口和 WorldFeed 8871 端口。
