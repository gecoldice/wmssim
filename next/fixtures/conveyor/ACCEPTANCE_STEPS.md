# P0.5 输送运行时 · 验收步骤（规范侧 · 仅直线）

编码：云端主线。本文件不宣称 pass。日期口径：Asia/Shanghai。

## 前置
1. 人工主路径 / MX-D*-EB 已收口（夹具仍可标 `spec_only`）。
2. 元素库正式速度字段：`speed_mpm`；引擎换算 `m/s = speed_mpm / 60`；禁止 `speed_m_s` 双主字段。
3. 直线段布局：每段 ≥1 in + ≥1 out；`ports[].id ⊆ connector_ids`。

## 步骤
1. 跑 `G-CV-01`：单 `CV-STR-01`，核对 enter→exit 时长 ≈ `length_m / (speed_mpm/60)`（容差工程约定，草案 ±5%）。
2. 跑 `G-CV-02`：STR 端点接驳到月台/货架 `accessNodeId`；同 `layoutRevision`；叉车仍走通道边占用；载荷走输送时段。
3. 逐案跑 `G-CV-03`：缺 connector / 断链 / 必经弯道或合流 / 未接 AGV / revision 不一致 → 拒跑 + 藏四卡，无假 KPI。
4. 可选草案 `MX-D1-CV`：`template.mixed_wh_v0` + ≥1 段 `CV-STR-01`；仍 `spec_only`；**≠** 替代 `MX-D1-EB` pass。

## 回放口径（E1/E2）
- E1：`segments` 可带 `mode=conveyor` 与 `elementId`；前端可播则播时间轴。
- E2：不强制看见辊子转；若无输送动画，界面不得暗示「已看见输送在动」。

## 与人工主路径 / MX-D*-EB
- 同画布、同 `layoutRevision`；输送图与通道图并存。
- 本刀 = 直线输送 DES 切片；不宣称 UA S-D1 全绿、不替代边占用/拆托金样。
