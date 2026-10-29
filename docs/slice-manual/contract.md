# 契约说明 · 人工摆放切片

运行中的 schema 在 `next/contracts/`。它从仓库既有 `contracts/schemas` 复制了本切片用到的 Snapshot 0.2、equip 0.2、Project、Facility、LayoutDocument、Demand、OperatingProfile、ScenarioPackage、ValidationReport。复制之后以 `next/contracts` 为准，旧目录不改。

外层 `contractVersion = "0.3"`。推演快照 `schemaVersion = "0.2"`。类型 ID 只接受 `ST-PAL-01` 这种正式 ID。短名在 schema 和 `POST /layouts/{id}/revisions` 都被拒绝（`ELEMENT_ID`）。

`layoutRevision` 由服务端签发，形如 `lr_` 加 16 位十六进制，只做字符串相等。浏览器不铸造修订。请求里的 `baseRevision` 或文档 `revision` 与已存修订不一致时返回 409 `REVISION_CONFLICT`，不覆盖。

前缀 `/api/v1`。准备和推演先返回 202 与 `jobId`，再 `GET /jobs/{id}`。计算在进程内线程中完成，响应体里当时的状态仍是 `queued`。

| 方法 | 路径 | 作用 |
|---|---|---|
| POST | `/projects` | 建项目 |
| GET | `/projects/{id}` | 刷新时读回项目。S-11 需要的读半边 |
| POST | `/projects/{id}/facility-revisions` | 保存场地 |
| GET | `/projects/{id}/facility` | 读回场地 |
| POST | `/layouts/{id}/revisions` | 保存布局并签发修订 |
| GET | `/layouts/{id}` | 读回最近一次已保存布局 |
| POST | `/layouts/{id}/prepare-jobs` | 派生并权威校验 |
| GET | `/jobs/{id}` | 准备或推演状态 |
| POST | `/simulation-jobs` | 绑定布局修订与场景。未准备通过则 409 |
| GET | `/runs/{id}` | 清单、四卡、事件、轨迹、`layoutRevision` |
| GET | `/health` | 存活探测。`planning` 为 false |

没有规划、采用、价目、成本、比较、识图。

`full_pallet` 与 `break_bulk` 可以推演。单独的 `piece_pick` 让作业失败（`UNSUPPORTED_SCENARIO`），不写入 run。拆托下游的小件只生成箱任务。四卡形状以 `schemas/slice/run-result.schema.json` 为准：利用率只有 `byResourceType` 与 `byResource`，没有无类型的 `value`。`kpiFromUiDemo` 固定为 false。没有成功的本次运行时，决策页不渲染主四卡。

相对复制来的错误码枚举，本切片追加了 `NOT_SIMULATION_READY`、`LAYOUT_REVISION_MISMATCH`、`ELEMENT_ID`、`NO_RESOURCES`、`NARROW_AISLE`。
