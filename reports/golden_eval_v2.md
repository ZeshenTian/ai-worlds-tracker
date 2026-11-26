# 盲测结果

| 组别 | 原帖抓到 | 通过筛选或已提取 | 最终命中或泄漏 | 样本 |
|---|---:|---:|---:|---:|
| positive_core | 8 | 8 | 8 | 9 |
| positive_long_tail | 0 | 0 | 0 | 0 |
| negative_controls | 1 | 0 | 0 | 5 |
| secondary_leads | 0 | 0 | 0 | 0 |
| borderline_review | 0 | 0 | 0 | 0 |

核心召回率 88.9%，原帖捕获率 88.9%。
长尾召回率 0.0%，原帖捕获率 0.0%。
负样本泄漏率 0.0%，以聚合号名义发布 0 条。
严格验收通过。

| 组别 | 帖子 | Raw | 信号 | 赞 | 通过筛选或已提取 | 筛选回执 | 案例审核状态 | 前沿公开 | 诊断 | 核查记录 |
|---|---|---|---|---|---|---|---|---|---|---|
| positive_core | 2124431846859813234 | True | True | 956 | True | accepted | approved | True | hit | — |
| positive_core | 2123306922971656549 | True | True | 283 | True | absent | approved | True | hit | — |
| positive_core | 2123826572385833119 | True | True | 4067 | True | absent | approved, pending | True | hit | — |
| positive_core | 2125331267512377844 | True | True | 120 | True | accepted | approved | True | hit | — |
| positive_core | 2125246059232235832 | True | True | 55 | True | declined | approved | True | hit | — |
| positive_core | 2119925633564463609 | True | True | 15057 | True | absent | approved | True | hit | — |
| positive_core | 2119901658394358005 | True | True | 143 | True | absent | approved | True | hit | — |
| positive_core | 2119573179773436153 | False | False | None | False | absent | 未提取 | False | missed_at_crawl | — |
| positive_core | 2118800755595292961 | True | True | 152 | True | accepted | approved | True | hit | — |
| negative_controls | 2125304202587234481 | True | True | 884 | False | declined | 未提取 | False | dropped_at_gate | — |
| negative_controls | 2123815052553650499 | False | False | None | False | absent | 未提取 | False | missed_at_crawl | — |
| negative_controls | 2113250176307536334 | False | False | None | False | absent | 未提取 | False | missed_at_crawl | — |
| negative_controls | 2125275658490204231 | False | False | None | False | absent | 未提取 | False | missed_at_crawl | — |
| negative_controls | 2119898687803621427 | False | False | None | False | absent | 未提取 | False | missed_at_crawl | — |
