# 验收步骤 · 综合仓边占用 + 拆托（MX-D1/D2/D3-EB）

夹具 `status` 保持 `spec_only`，脚本不会把它改成 pass。退出码 0 只表示这三份夹具的断言成立。

不等于 UA S-D1 / S-D2 / S-D3 已过，不等于综合仓三流人路径全绿，不等于业务接量成立，也不等于 G-EDGE / G-BREAK 可以代替这三份。

## 命令

```bash
PYTHONPATH=next python3 next/scripts/run_mx.py
PYTHONPATH=next python3 next/scripts/run_gold.py
PYTHONPATH=next python3 next/scripts/accept_slice.py
```

`accept_slice.py` 会带上 `run_mx.py` 和 `run_gold.py`。

## 步骤

1. 导出 `template.mixed_wh_v0` 布局（`next/web/scripts/export-mixed-layout.mjs`），派生 `schemaVersion=0.2`，`layoutRevision=mx-wh-rev-eb`。提交的布局字节须与这次导出一致。
2. 跑 MX-D1-EB。`edgeOccupancy.enabled=true`。流为整托 50、拆托 30、小件 20（`generate_only`）。班次 8 小时，种子 42。到达窗在夹具里写成 60 秒，用来让 3 台叉车叠在 `maxConcurrent=2` 的通道边上；这不是 8 小时均匀到达。
3. 核对：库存守恒、完成拆托托数 × `casesPerPallet` = 箱、存在 occupy 事件、主四卡是有限数、轨迹段非空、箱任务可以不是 done。不核对「接得住多少托」这种业务目标。
4. 跑 MX-D2-EB。同一 `layoutRevision`，叉车 3 再跑 2。记录吞吐或等待的差别。禁止两套四卡逐字段相同还没有说明。
5. 跑 MX-D3-EB 四案：修订不一致、去掉拆托站、货位缺 `accessNodeId`、删掉通道边。每一案加载失败即停，不返回四卡。

`rack-001` 的 `palletsPerBay` 在派生前从 2 改成 20，只为装下 80 托初始库存。占地 pose 仍是模板的。这不是物理货格已经按 80 托建完。
