# 盲测结果

| 组别 | 原帖抓到 | 通过筛选或已提取 | 最终命中或泄漏 | 样本 |
|---|---:|---:|---:|---:|
| positive_core | 11 | 11 | 10 | 11 |
| positive_long_tail | 1 | 1 | 1 | 5 |
| negative_controls | 2 | 0 | 0 | 3 |
| secondary_leads | 2 | 0 | 0 | 5 |
| borderline_review | 1 | 1 | 0 | 1 |

核心召回率 90.9%，原帖捕获率 100.0%。
长尾召回率 20.0%，原帖捕获率 20.0%。
负样本泄漏率 0.0%，以聚合号名义发布 0 条。
严格验收通过。

| 组别 | 帖子 | Raw | 信号 | 赞 | 通过筛选或已提取 | 筛选回执 | 案例审核状态 | 前沿公开 | 诊断 | 核查记录 |
|---|---|---|---|---|---|---|---|---|---|---|
| positive_core | 2123009738921414788 | True | True | 1218 | True | accepted | approved | True | hit | — |
| positive_core | 2125293653195415776 | True | True | 119 | True | accepted | approved | True | hit | — |
| positive_core | 2123794210721804750 | True | True | 948 | True | accepted | approved | True | hit | — |
| positive_core | 2123306526878437857 | True | True | 481 | True | accepted | approved | True | hit | — |
| positive_core | 2125140294530453981 | True | True | 40 | True | accepted | approved | True | hit | — |
| positive_core | 2125368341002924390 | True | True | 173 | True | accepted | pending | False | stuck_in_pending | 作者、模型用法或作品类型的证据不足 |
| positive_core | 2125226204764733481 | True | True | 3402 | True | accepted | approved | True | hit | — |
| positive_core | 2125327793517146539 | True | True | 610 | True | accepted | approved | True | hit | — |
| positive_core | 2123506487792410706 | True | True | 91 | True | accepted | approved | True | hit | — |
| positive_core | 2124899361200931069 | True | True | 40 | True | accepted | approved | True | hit | — |
| positive_core | 2125329103289299194 | True | True | 105 | True | accepted | approved | True | hit | — |
| positive_long_tail | 2124540914093944951 | False | False | None | False | absent | 未提取 | False | missed_at_crawl | — |
| positive_long_tail | 2125430353494225069 | True | True | 2 | True | declined | approved | True | hit | — |
| positive_long_tail | 2123475576271012121 | False | False | None | False | absent | 未提取 | False | missed_at_crawl | — |
| positive_long_tail | 2123237325765325155 | False | False | None | False | absent | 未提取 | False | missed_at_crawl | — |
| positive_long_tail | 2124438422790254807 | False | False | None | False | absent | 未提取 | False | missed_at_crawl | — |
| negative_controls | 2124998123210891290 | True | True | 306 | False | declined | 未提取 | False | dropped_at_gate | — |
| negative_controls | 2123698922170564671 | False | False | None | False | absent | 未提取 | False | missed_at_crawl | — |
| negative_controls | 2123538258265075804 | True | True | 1324 | False | absent | 未提取 | False | dropped_at_gate | — |
| secondary_leads | 2124877629966709080 | False | False | None | False | absent | 未提取 | False | missed_at_crawl | — |
| secondary_leads | 2124108900299382873 | False | False | None | False | absent | 未提取 | False | missed_at_crawl | — |
| secondary_leads | 2123745767286276410 | True | True | 661 | False | absent | 未提取 | False | dropped_at_gate | — |
| secondary_leads | 2123023253182586966 | False | False | None | False | absent | 未提取 | False | missed_at_crawl | — |
| secondary_leads | 2122658959022502304 | True | True | 287 | False | absent | 未提取 | False | dropped_at_gate | — |
| borderline_review | 2125350497238610336 | True | True | 317 | True | accepted | 未提取 | False | stuck_in_pending | — |
