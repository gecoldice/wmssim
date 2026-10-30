# P0.5 输送运行时（本刀仅直线）

| 文件 | 用途 |
|------|------|
| G-CV-01.json | 单直线 CV-STR-01，in→out 时长可核 |
| G-CV-02.json | STR 端点接驳月台/货架 accessNode 混布 |
| G-CV-03.json | 拒载/未接多案集合 |
| MX-D1-CV.json | mixed_wh + ≥1 段 CV-STR 旁路草案 |
| ACCEPTANCE_STEPS.md | 验收步骤 |

全部 `status: spec_only`。云端主线编码接测前不得标 pass。

**本刀子集会（已接）**：`CV-STR-01` · `CV-ROL-01` · `CV-BELT-01`  
**非本刀（必经则拒跑藏四卡）**：`CV-CURVE-01` · `CV-MERGE-01` · `CV-DIV-01` · `CV-BUF-01` · `CV-VERT-01` · `CV-CHUTE-01` · `CV-LOOP-01` · `CV-INDUCT-EACH-01`  
**外延**：AGV=P0.5b · ASRS=P1b · CV-INDUCT=P1
