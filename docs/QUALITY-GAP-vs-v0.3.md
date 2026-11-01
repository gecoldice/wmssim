# 质量差距报告 · 当前 simapp 对照总体设计 v0.3

日期：2026-10-29。对照材料是本轮解包的 v0.3 设计（00–07），实现是分支 `cursor/m5-workbench-ui-5ace`（HEAD `0d30872`）上的工程根。仓库里没有单独的 `simapp/` 子目录，本文件放在工程根 `docs/`。

本文只记录已读到的设计和已跑过的程序。设计里的验收项仍是**待实现/待测**。下文“脚本通过”不等于“AC 已验收”。

## 0. 结论

**推荐 C：按新的单主线重做。种子只保留契约、夹具和它们已经锁住的不变量。不在现有工作台和 API 上继续拼。**

用户已确认整体重做，不要 salvage 旧 simapp 拼装路线。B（留引擎、只重写 UI）仅在 DES 与契约明显可原样当产品内核时成立。核对之后，这个条件不成立。详见 §8。重写范围、目录和第一条编码切片见 [REWRITE-PLAN-manual-slice.md](REWRITE-PLAN-manual-slice.md)。

本轮不删代码，不改运行时行为。

| 选项 | 判定 | 理由 |
|---|---|---|
| A 手术修补 | 否 | 产品缺口是页面和任务模型整段缺失，补在 `App.tsx` / `main.py` 上会继续加厚两个上帝文件。 |
| B 留引擎、重写 UI | 否 | 事件循环是真的，但决策四卡口径和任务边界已经偏离 05/06。只换皮会把这套口径带进新界面。 |
| C 新主线，保留契约与夹具 | **是** | Schema、正反例和守恒/门禁断言可以当种子。产品壳、同步 API、浏览器里铸造的修订号、演示价目主按钮全部离开运行路径。 |

## 1. 这次怎么核对的

- 读了 v0.3：00 决策、01 流程、02 边界、03 页面、05 指标、06 契约、07 任务与 AC。
- 读了工作台、文档拼装、API、派生/校验、规划器、DES、成本/比较，以及 `scripts/run_m*.py`。
- 2026-10-29 在本机安装 `services/api/requirements.txt` 后实跑（退出码均为 0）：

```text
validate:fixtures  PASS（全部夹具 + 坐标变换）
test:m1            All M1 derive/validate checks passed.
test:m2            All M2 planning/adopt checks passed.
test:m3            All M3 checks passed.
test:m4            All 7 M4 checks passed.
test:m5            All 10 M5 checks passed.
test:persist       PASS sqlite reload
```

仓库内没有 `*.test.ts` / `*.spec.ts` / pytest 文件。所谓测试就是上述脚本。没有打开浏览器走工作台，因为本轮交付的是差距和重写计划，不是界面补丁。

## 2. 产品契合（01 / 03）

v0.3 主路径是：摆布局 → 推演 → 修改 → 再推演。自动规划是工作台里的可选动作。单方案决策看吞吐、等待（均值和 P95）、利用率、瓶颈 TopN。成本在多方案页，是次级。

当前工作台把三栏和三个页签搭出来了，主路径在按钮层存在。客户实际走完时，决策信息和页面状态都对不上 03。

| 设计 | 代码现状 | 证据 |
|---|---|---|
| UI-01 项目与方案列表 | 启动时按名称「工作台方案」取最近一个项目，没有列表、复制、分支抽屉 | `apps/web/src/App.tsx` 恢复逻辑 |
| UI-02 工作台：摆放、保存、派生、校验、推演分开 | 有左库、中画布、右参数和「校验并准备 / 开始推演」。保存、派生、校验、结果有效性合成一颗状态药丸 | `App.tsx` `saveLabel`；03 §2 写明不能用一个 dirty 代表四件事 |
| 空画布三个起点，已有布局不弹向导 | 文案提到三种起步。自动生成是工具条按钮加大抽屉，不是强制向导。这一点符合 DEC-01 | `App.tsx` 工具条与 `planOpen` |
| 画布按实际尺寸编辑，非法落点拒绝并恢复 | 点击落点，数值可改。没有拖拽。落点只夹在场地矩形内，碰撞要等准备接口 | `onCanvasClick`、`place` |
| 撤销/重做、版本抽屉 UI-09 | 只有内存撤销栈，无重做，刷新后撤销历史消失。布局 `parentRef` 由浏览器固定写成 `null` | `history` ref；`documents.ts` `buildLayout` |
| UI-03 标定/描边/确认场地 | 没有这页。右栏是「复杂识图」表单，调用必失败的 M5 接口 | `App.tsx` 识图区；`simapp_extend/recognition.py` |
| UI-04 四步向导，缺数据时目标禁用并说明 | 抽屉里一个按钮「按容量目标生成」。需求写死库存目标 48 托，日出入不采集 | `buildPlanningDemand`；`onPlan` |
| UI-05 候选大图、修改范围、preliminary/validated 文案 | 候选是 id 加几何库容一行字，没有图，没有差分 | `candidates.map` |
| UI-06 业务/资源/运行设置独立于布局 | 出库托数和叉车数直接铺在未选中时的右栏，和场地尺寸混在一起 | 右栏「场地与推演输入」 |
| UI-07 四卡 + 完成率/积压 + 回放绑定历史布局 + 导出 | 四卡数字来自接口，完成率有。回放时间轴没有。导出按钮没有。结果页主按钮是「估算成本并对比叉车加一」 | `view === "results"` |
| 利用率按资源类型分列；瓶颈 TopN | 引擎给一个混合利用率。界面只渲染 `top1` | `kpi.py`；结果页瓶颈卡 |
| 结果过期：布局/需求/价格分开 | 仅当本地 `dirty` 或 `layoutRevision` 字符串不等时出一句警告。改出库量不置脏 | `outboundQty` 的 `onChange` 不调用 `setDirty` |
| UI-08 自选 2–4 套方案，layout_only / whole_solution，雷达 | 对比固定克隆当前几何，叉车数 +1，模式写死 `whole_solution`。雷达是文本，不是图 | `onCostCompare`、`ALT_LAYOUT_ID` |
| UI-10 任务阶段、取消、恢复 | 准备/规划/推演在同一次 HTTP 里算完。界面是「请求中…」 | `main.py` `prepare_layout`、`create_simulation_job` |
| 跨页空态/失败/过期/并发文案（03 §8） | 有少量中文提示。没有标定缺失、无候选搜索预算、并发另存、断网草稿这几条的页面 | 对照 03 §8 |
| 视觉 | 03 规定浅底青绿工作台。当前是浅色表单（`--bg:#f3f6f5`，14px）。前序产品意图另要求深色数字孪生 HUD。两套视觉都没有做成可用的工作台 | `styles.css` |

主路径能点通，是因为浏览器在一次点击里串行调用了保存、准备和推演。这不是 01 的「先得到可编辑布局，再对不可变版本推演」。

## 3. 架构（02 / 06）

Python 包的名字对齐了 02 的数据所有权：`simapp_derive`、`simapp_validate`、`simapp_plan`、`simapp_des`、`simapp_cost`、`simapp_compare`、`simapp_extend`。这是目录划分，不是运行边界。

| 02/06 要求 | 现状 |
|---|---|
| 一个应用 API + 可独立运行的计算 worker，推演不堵住 HTTP | `services/worker/main.py` 只做能力探测。派生、规划、DES、成本都在 FastAPI 请求里算完，HTTP 状态仍标 202。OpenAPI 自己写着 “M1 sync completes in response” |
| 前端预检，后端权威校验 | 浏览器不做几何预检。权威校验在 `prepare-jobs`，但客户端要传 `sync: true` |
| 不可变修订由服务端签发，revision 只做相等比较 | 相等比较在 DES 里做到了（`LAYOUT_REVISION_MISMATCH`）。修订字符串由浏览器 `Date.now()` 铸造后交给服务端保存 |
| 工作副本与不可变版本分开；`parentRef` 形成分支 | 工作台每次保存都把 `parentRef: null` 写进场地、布局、需求、资源 |
| 输入指纹决定过期，保存布局不会让旧跑次变新 | 库里准备结果可以标 `stale`（`store.py`）。工作台不按指纹区分几何过期、需求过期、价格过期 |
| 幂等键、取消、乐观锁 | 采用冲突有 409（m2 脚本覆盖）。全库没有 `Idempotency-Key`。取消接口存在，主路径不经过排队 |
| 合同一处生成两端类型 | 有 JSON Schema、OpenAPI、`packages/contracts-ts`。工作台另写了一套 `Cards` / `WorkspacePayload`，需求文档在 `documents.ts` 再拼一份 |
| 图纸项目级授权（AC-21） | 读接口凭 id。无项目隔离测试 |

上帝文件（行数，含实现）：

| 文件 | 行数 | 问题 |
|---|---|---|
| `apps/web/src/App.tsx` | 1409 | 恢复、编辑、准备、推演、规划、采用、识图、成本对比、三块界面在一个组件 |
| `services/api/app/main.py` | 1429 | 全部路由和编排 |
| `services/api/app/store.py` | 740 | 内存/SQLite 混在一个存储 |
| `shared/python/simapp_des/engine.py` | 901 | 相对内聚，但是唯一的运营模型 |
| `apps/web/src/documents.ts` | 406 | 第二份演示数据：48 托规划需求、demo 价目、打开的故障注入 |

`apps/web/src/library.ts` 与 `simapp_derive` 的默认占地各写一遍，注释要求人工保持一致。

## 4. 引擎诚实性

DES **不是**把 `03-UI原型` 的货架数公式搬进后端。`kpi.py` 从完成任务和事件计数。m3 脚本断言：同输入两次结果一致、快照不被改写、库存守恒、外部发运 4 托、`kpiFromUiDemo === false`、出库证据能对上 `eventId`。`engine.py` 使用 `heapq` 事件队列、最短路、边容量排队、`InventoryLedger`。

因此不能写成「仿真是假数字」。问题是模型窄，而且决策口径与 05 不一致，脚本没有把 05 的口径锁死。

| 05 / 12 口径 | 实现 | 后果 |
|---|---|---|
| P95：n=0 为 null；n≥1 用 nearest-rank `ceil(0.95×n)` | `kpi.py` 在 **n<20 时不报 P95**。这是提交 `60dbc66`（说明：样本小时省略 P95）的实现选择，不是漏写 | 工作台默认出库 4 托（`useState(4)`）。主路径上 P95 永远是空。m3 不断言 `p95Sec` 的值，所以测试仍绿 |
| 利用率按资源类型 | `busySec 合计 / (资源数 × horizon)`，一个数 | 03 §6 禁止只给混合平均 |
| 瓶颈 TopN，未完成等待另列 | 引擎有 `topN`（最多 5）。UI 只用 `top1`。无等待时 `waitSec: 0` | 0 与「无样本」容易混 |
| 无需求时完成率 null，无完成任务时等待 null | m3 零需求夹具断言等待均值是 null、完成任务 0。完成率分母为 0 时引擎返回 null | 这条库行为与 05 一致，有脚本 |
| 拆托下游只计一次外部发运（AC-18） | `flowKind != full_pallet` 时警告 `FLOW_KIND_STUB` 并跳过 | 综合仓若含拆托，吞吐不完整。脚本未覆盖 |
| 班次、技能、故障 | 工作台 `buildOperating` **每次**带 `skillTags: ["certified"]` 和 `faults.enabled: true`。引擎忽略并打警告 | 主路径跑次永远带「已忽略」警告，客户无法区分真警告 |
| 到达过程 | 均匀整托，种子写入清单但不驱动随机 | 可复现。不能代表高峰 |
| 金样 KPI | `fixtures/meta/catalog.json` 写明「本目录不含猜测 KPI 期望值」 | 正确态度。同时也说明四卡数字从未锁定 |

规划器是矩形场地上的模板枚举加派生校验，输出可编辑的 `ST-PAL-01`，并声明 `claimsOperationalEfficiency: false`。m2 断言候选数 ≤4、锁定元素不动、未确认场地不能进入 validated。它不是 04 的约束搜索，也没有搜索预算耗尽的脚本。快速评估不能当运营效率，代码和测试在这点上是诚实的。它不属于本报告要保留的主线引擎：第一条切片不做自动规划。

成本与比较库对「缺价不参加最低成本」「缺轴不补零」「layout_only 资源不一致则不可比」有断言。工作台把 demo 价目当成对比主路径，并把「同一布局、叉车加一」称作方案对比。库的诚实没有到达页面。

## 5. 契约 fidelity

对齐的部分：

- 外层 `contractVersion = "0.3"`，Snapshot `schemaVersion = "0.2"`，equip `schema_version = "0.2"`。
- 短名 alias 夹具 `bad-equip-short-alias.json` 被 schema 拒绝。正式类型 ID 有正例 `ST-PAL-01`。
- `layoutRevision` 在 DES 入口做字符串相等，不相等即 `LAYOUT_REVISION_MISMATCH`（m3）。
- 派生后的 `accessNodeId` 必须指向存在的节点；跨墙夹具 `NO_ACCESS_NODE`（m1）。
- 坐标注释与夹具检查：平面米，X 东 Y 北，3D `(x, 高度, -y)`。

偏离的部分：

- 06 的异步任务（排队、取消中、幂等键、202 只返回 jobId）在主路径上是同步函数加 202。
- 工作台不提交 `parentRef`，版本链在 UI 写入侧是断的。采用规划候选时，`simapp_plan/adopt.py` 会写 parent，这条只存在于自动规划。
- 06 的比较重算 `POST /comparisons/{id}/evaluation-jobs` 未作为工作台路径。工作台直接再跑一遍 DES 再 `POST /comparisons`。
- 报告接口 `POST /reports` 有 m4 绑定修订的脚本。界面没有入口。
- 错误码在 `packages/contracts-ts` 里列了 `STALE_VALIDATION` 等。工作台把异常 `message` 摊成一条红字。

## 6. 测试现实

脚本证明的是库和 TestClient 上的性质。07 的 22 条 AC 里，多数没有页面走查，有几条设计夹具根本没有建。

设计 07 §4 的 FX-03（能放下但转不过弯）、FX-04/05（锁定与区域）、FX-06（混合货位有效库容）、FX-08（工位队列）、FX-09（加非瓶颈货架不增加吞吐）、FX-10（币种/重复计费）、FX-11（去重）、FX-12（与穷举最优的差距）在 `fixtures/` 中没有对应条目。校验器规则只有碰撞、窄通道、accessNode、可达性（`GEOMETRY_INVALID`、`NARROW_AISLE`、`NO_ACCESS_NODE`、`ROUTE_UNREACHABLE`）。没有转向不足，没有单向断路。

| AC | 脚本实际覆盖 | 未覆盖 |
|---|---|---|
| AC-01 不经自动规划完成摆放并推演 | m3：先 prepare 才允许 DES | 无浏览器路径。无人机验收 |
| AC-02 缺比例不得输出精确布局 | m5：识图不写场地 | 无标定页 |
| AC-03 日量未知则效率/成本目标不可用 | 无 | 向导不采集日量 |
| AC-04 硬约束候选、不足 4 不凑数 | m2：该夹具得到 4 个货架布局，断言 ≤4 | 没有「只能得到 1 个」的夹具来证明不改名凑数 |
| AC-05 锁定与区域外不变 | m2 locks 通过 | UI 无局部重排 |
| AC-06 采用后与手动同一编辑/撤销 | 无 | 无拖拽；撤销不入库 |
| AC-07 生成期间改布局，候选标旧来源 | m2：错误修订号返回 409 | UI 不显示「基于较早版本」 |
| AC-08 同输入可复现 | m3 引擎与 API 各一次 | 成立 |
| AC-09 同吞吐不能当成同效率 | 无 | 对比主路径不改布局 |
| AC-10 layout_only / whole_solution | m4 函数级断言 | UI 只提交 whole_solution，且两套几何相同 |
| AC-11 加方案不改旧分 | m4 | UI 不能加方案 |
| AC-12 缺轴不补零，不足 3 轴只出表 | m4 | UI 无雷达图，只有点数文本 |
| AC-13 零需求不伪造等待 | m3 | 库行为成立 |
| AC-14 新购/搬移/运营分列 | m4 | UI 使用 demo 价目，无既有资产流程 |
| AC-15 无候选是 no_feasible_found | `planner.py` 有该分支 | 脚本未走到 |
| AC-16 取消、刷新、幂等 | 无 | 无 |
| AC-17 跨墙、单向、转向 | m1 跨墙与窄通道 | 无转向、无单向 |
| AC-18 拆托发运只计一次 | 无 | 非整托被跳过 |
| AC-19 只改价格或只改需求的过期 | 无 | UI 脏标记不覆盖需求 |
| AC-20 历史回放用历史布局 | m3：`replayBinding.layoutRevision` 等于该次修订 | 无回放画面。绑定字段存在 |
| AC-21 猜不到其他项目 | 无 | 无授权 |
| AC-22 非法导入、断网、保存失败 | persist：SQLite 重启后跑次还在 | 无断网与失败文案走查 |

m5 的 10 条全绿，内容是「DXF / OCR / 多边形 / NSGA-II / 长期成本返回失败」。这证明未实现能力没有被假装算完，也证明这些检查不增加主路径质量。识图表单仍放在主右栏。

## 7. 技术债密度

高，而且集中在客户唯一看得见的文件里。

- 一个组件承担 M1–M5 的全部界面。后续每次里程碑都加状态字段，没有按 03 的组件边界拆开。
- 演示数据有三处：元素库、`documents.ts` 的价目/48 托/故障注入、规划器里的货架尺寸常数。
- 不支持的能力以可点击表单出现（识图、以及结果页上唯一的「方案」动作是叉车加一）。
- 契约类型与 UI 类型重复，字段一改不会在编译期同时失败。
- 测试绿色覆盖了库的守门，没有覆盖 03 的页面状态。读 README 会得到「工作台已能四卡和对比」的印象；读 07 的 AC 则多数仍是未测。

## 8. 为什么不是 B

已经核实、然后放弃的判断：

1. 「DES 是演示公式」——不成立。事件队列、库存账、守恒断言、出库事件证据都在，m3 通过。
2. 「契约文件不存在」——不成立。`contracts/schemas/v0.2` 与 `v0.3`、OpenAPI、夹具校验都在，且 `validate:fixtures` 通过。
3. 「所以应该留引擎只重写 UI」——不成立。可复用的是 **种子**，不是 **运行中的产品内核**：
   - 决策卡 P95 被 n<20 规则拿掉，默认主路径样本就是 4。这是 05 的直接冲突，m3 没锁住。
   - 利用率是混合平均，界面没有 TopN。
   - 工作台自己提交的技能标签和已启用故障被引擎丢弃，每次运行都在警告。
   - 任务模型与 06 不一致：同步计算、浏览器铸造修订、工作台写入的 `parentRef` 恒为 null。
   - UI 若只是重画 `App.tsx` 的三栏，仍会调用这套请求拼装（`onCostCompare` 约 150 行在浏览器里造第二套布局和 demo 价）。

B 成立的条件是：四卡定义与 05 一致，并且 API 只做版本与鉴权、计算在 worker。现在两条都不成立。新切片里的 DES 可以阅读旧 `engine.py` 的事件阶段划分当作对照，禁止 `import simapp_des` 作为新运行时。旧进程保持原样，直到新切片有自己的金样。

## 9. 本轮没有做的事

- 没有删除或停用旧工作台、API、脚本。
- 没有改 KPI、没有改 UI。
- 没有把任何 AC 标成已验收。
- 没有做 DXF、OCR、NSGA-II，也没有做视觉换皮。
