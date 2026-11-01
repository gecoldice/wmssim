# 输送运行时 · 验收步骤（规范侧）

编码：云端主线。本文件不宣称 pass。日期口径：Asia/Shanghai。

## 前置
1. 人工主路径 / MX-D*-EB 已收口（夹具仍可标 `spec_only`）。
2. 元素库正式速度字段：`speed_mpm`；引擎换算 `m/s = speed_mpm / 60`；禁止 `speed_m_s` 双主字段。
3. 直线段布局：每段 ≥1 in + ≥1 out；`ports[].id ⊆ connector_ids`。

## 步骤
1. 跑 `G-CV-01`：单 `CV-STR-01`，核对 enter→exit 时长 ≈ `length_m / (speed_mpm/60)`（容差工程约定，草案 ±5%）。
2. 跑 `G-CV-02`：STR 端点接驳到月台/货架 `accessNodeId`；同 `layoutRevision`；叉车仍走通道边占用；载荷走输送时段。
3. 逐案跑 `G-CV-03`：缺 connector / 断链 / 合流只有一个入口 / 分流只有一个出口 / 缓冲没填位数 / 未接垂直滑槽环线诱导口 / 未接 AGV / revision 不一致 → 拒跑 + 藏四卡。弯道接在直线前应跑通。
4. `G-CV-04`：弯道 3 m @ 30 mpm = 6 s。
5. `G-CV-05`：合流 6 m @ 30 mpm，两托等待 0 与 12 s，均值 6，P95 12，吞吐 24 palletEq/h。
6. `G-CV-06`：去向 B 的轨迹只有分流口和 B 支路，全程 12 s，A 支路不出现。
7. `G-CV-07`：缓冲位数 1 与合流同数字；位数 2 时两托同时进入、等待为 0。
8. 可选草案 `MX-D1-CV`：`template.mixed_wh_v0` + ≥1 段 `CV-STR-01`；仍 `spec_only`；**≠** 替代 `MX-D1-EB` pass。

## 回放口径（E1/E2）
- E1：`segments` 可带 `mode=conveyor` 与 `elementId`；前端可播则播时间轴。
- E2：不强制看见辊子转；若无输送动画，界面不得暗示「已看见输送在动」。

## 与人工主路径 / MX-D*-EB
- 同画布、同 `layoutRevision`；输送图与通道图并存。
- 本刀 = 直线输送 DES 切片；不宣称 UA S-D1 全绿、不替代边占用/拆托金样。
