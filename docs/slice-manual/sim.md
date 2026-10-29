# 仿真说明 · 人工摆放切片

新引擎在 `next/des/`。它不引用旧引擎包。只接受 `flowKind = full_pallet`，否则 `UNSUPPORTED_SCENARIO`，没有吞吐。

速度、取货秒、发运秒、评价时长必须由调用方给出。缺了就拒绝，引擎不填默认值。夹具里的 1.5 m/s、1.2 m/s、10 秒、5 秒和 4 托都标明为测试值。

## 事件

出库一托的阶段：`arrival`、可能的 `resource_wait`、`dispatch`、空驶 `travel_start` / `travel_arrive`、`pick`、载货行驶、`ship_start`、`ship`、`task_complete`。

`ship.palletEq` 只在外部发运完成时记 1。叉车占用从派发到完成，含行驶。拣选资源不接整托，利用率为 0，单独成列。

到达是窗口内的均匀整数时刻。种子写入清单，不给到达加随机抖动。同一快照、同一场景、同一资源，两次事件序列一致，而且不改快照字节。

## 库存

`initial + inbound = ending + inTransit + outbound`。残差须为 0。

## 四卡

- 吞吐：外部发运托当量 / (horizonSec / 3600)。时长不是正数则为 null。
- 等待：只统计已完成任务。n = 0 时均值和 P95 都是 null。n ≥ 1 时 P95 为升序后的第 `ceil(0.95 × n)` 个（1-based）。样本小于 20 也照报。
- 利用率：按资源类型，并按资源 id 分列。没有一个无类型的混合比。
- 瓶颈：正等待按实体汇总的 `topN`。没有正等待时是空数组，不用 0 秒占位。
- 完成率：没有任务时为 null。

`kpiFromUiDemo` 恒为 false。

## 金样

小样本（4 托，一台叉车，评价 3600 秒）的期望数在跑完事件并对照 `next/fixtures/manual-wh/hand-check.md` 之后写入 `expected-cards.json`，`engineVersion` 为 `slice-des-0.1`。核对前夹具里没有这五个数。第一托从收货端空驶 10 m；之后叉车停在发货端，空驶改为 26 m。因此等待均值是 131/2 秒，P95 是 409/3 秒，而不是「每托都从月台出发」的那组数。
