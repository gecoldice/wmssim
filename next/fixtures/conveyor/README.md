# P0.5 输送运行时（本刀仅直线）

| 文件 | 用途 |
|------|------|
| G-CV-01.json | 单直线 CV-STR-01，in→out 时长可核 |
| G-CV-02.json | STR 端点接驳月台/货架 accessNode 混布 |
| G-CV-03.json | 拒载/未接多案集合 |
| G-CV-04.json | 单弯道，3 m @ 30 mpm = 6 s |
| G-CV-05.json | 合流同时 1 托，第二托等待一个行程 |
| G-CV-06.json | 分流只走去向支路 |
| G-CV-07.json | 缓冲位数 1 与合流同等待；位数 2 可同时进入 |
| MX-D1-CV.json | mixed_wh + ≥1 段 CV-STR 旁路草案 |
| ACCEPTANCE_STEPS.md | 验收步骤 |

全部 `status: spec_only`。断言通过不得改成 pass。

**已接**：`CV-STR-01` · `CV-ROL-01` · `CV-BELT-01` · `CV-CURVE-01` · `CV-MERGE-01` · `CV-DIV-01` · `CV-BUF-01`  
**仍拒跑**：`CV-VERT-01` · `CV-CHUTE-01` · `CV-LOOP-01` · `CV-INDUCT-EACH-01`  
**外延**：CV-INDUCT。AGV 沿通道走，立体库按节拍取货，都不在输送段里。
