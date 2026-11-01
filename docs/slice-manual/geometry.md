# 几何说明 · 人工摆放切片

准备任务从布局文档和场地派生 Snapshot 0.2，再做权威校验。不自动摆放。

坐标系：场地西南角为原点，X 向东，Y 向北，单位米。

派生：

- 通道中心线变成节点和双向边。边穿过障碍则不生成。
- 设备中心投影到最近的通道中心线。8 米以内、且直线不穿障碍，才绑定 `accessNodeId`。
- 货架容量 = 层数 × 列数 × 每列托数。`ST-PAL-01` 占地 2.7 m × 1.2 m，月台 3 m × 4 m。

校验失败时不能推演：

| 规则 | 反例 | 正文 |
|---|---|---|
| 跨墙 | `layout-cross-wall.json` + `facility-wall.json`。货架 `rack-west` 在墙西，通道在墙东，8 米内的节点被墙挡住 | 含实例 `rack-west`，并写明跨墙 |
| 窄通道 | `layout-narrow.json`。通道宽 2.0 m，货架声明 `minClearWidthM` 3.0 m | `NARROW_AISLE` |
| 出界 / 重叠 | 占地超出场地矩形，或两台设备 AABB 相交 | `GEOMETRY_INVALID`，含实例 id |
| 无路 | 货位接入点到发货月台没有最短路 | `ROUTE_UNREACHABLE` |

转向半径和单向通道本切片不判断。
