# simapp · 仓库布局规划与运营推演

工程根：`/Users/lovewinnie/wmssim/simapp`  
方案权威：`/Users/lovewinnie/wmssim/simulation`（尤其 `04-总体与详细设计/` v0.3）  
远程：`https://github.com/gecoldice/wmssim.git`，分支 `cursor/m5-workbench-ui-5ace`。

**当前阶段：本地持久化 + 工作台成本对比** — 在 M1–M5 之上。

- 项目、布局、准备结果、跑次、成本和比较：设置 `DATABASE_URL=postgresql://...` 且不设 `SIMAPP_DB` 时写入 PostgreSQL；否则写入 `data/simapp.sqlite`。`SIMAPP_DB=off` 时测试仍用内存。显式 `SIMAPP_DB` 路径始终是 SQLite。
- 工作台：左元素库 / 中画布 / 右参数。摆放或采用候选 → 保存 → 校验并准备 → DES 四卡 → 成本/对比（当前方案 vs 叉车加一，`whole_solution`）。
- 四卡、库容、初投和对比表只显示接口结果。不使用 `03-UI原型` 的演示公式。价目是 `demoOnly` 输入。
- DEV-15 识图（DXF / OCR / 多边形分区）与 DEV-16（NSGA-II、多目标、长期成本、扩容/运维量表、未校准自动化）仍只返回失败或不支持，本切片不再追加这类桩。

> M3 DES 仍是运营效率证据。M2 `evaluationLevel=quick` 只是几何/路径估算。M4 缺价不排最低成本，缺轴不补分。

## 版本口径

| 层 | 版本 |
|---|---|
| 外层对象 | `contractVersion = "0.3"` |
| 布局 Snapshot | `schemaVersion = "0.2"` |
| equip.json | `schema_version = "0.2"` |
| 派生器 | `derivationVersion = m1-derive-0.1` |
| 规划器 | `plannerVersion = m2-plan-baseline-0.1` |
| DES 引擎 | `engineVersion = m3-des-0.1`（含 `full_pallet` / `break_bulk` / `piece_pick`；拆托中间产出不计外部吞吐） |
| 成本引擎 | `costEngineVersion = m4-cost-0.1` |
| 比较引擎 | `compareEngineVersion = m4-compare-0.1` |
| 扩展切片 | `extendVersion = m5-extend-0.1`（能力未实现） |
| 指标定义 | `metricDefinitionVersion = metrics-m3-v1` |

坐标：平面米制，原点仓房西南角，**X 东 Y 北**；3D `(X,Y,Z)=(x, 高度, -y)`。画布北在上。

## 目录

```text
simapp/
├── apps/web/                      # 布局工作台（库 / 画布 / 参数 / 四卡）
├── services/api/                  # FastAPI
├── services/worker/               # 能力探测（识图与 NSGA-II 标为未实现）
├── contracts/
├── packages/contracts-ts/
├── shared/python/
│   ├── simapp_derive/ simapp_validate/ simapp_plan/
│   ├── simapp_des/ simapp_cost/ simapp_compare/
│   └── simapp_extend/             # M5 失败/不支持路径
├── fixtures/{valid,invalid}/
├── data/simapp.sqlite            # 本地库（gitignore，运行 API 时生成）
└── scripts/run_m1_checks.py … run_m5_checks.py、run_persist_checks.py
```

## 本地运行

### 1. 依赖

```bash
cd /Users/lovewinnie/wmssim/simapp
npm install
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r services/api/requirements.txt
```

### 2. 校验与测试

```bash
source .venv/bin/activate
npm run validate:fixtures
npm run test:m1
npm run test:m2
npm run test:m3
npm run test:m4
npm run test:m5
npm run test:persist
npm run test:pg
npm run build:web
```

### 3. API 与工作台

```bash
source .venv/bin/activate
npm run dev:api
# 另一个终端
npm run dev:web
```

- API：http://127.0.0.1:8000/api/v1/health （`milestone=M5`，`persistence.engine=sqlite`）
- 工作台：http://127.0.0.1:5173
- 数据库：默认 `data/simapp.sqlite`（已 gitignore）。PostgreSQL：`DATABASE_URL=postgresql://USER:PASSWORD@127.0.0.1:5432/simapp npm run dev:api`（不要把口令写进仓库）。只切 SQLite 文件：`SIMAPP_DB=/path/to/file.sqlite npm run dev:api`。`npm run test:pg` 会拉起一次性 Docker Postgres 做切换验证。

主路径：

1. 「使用矩形模板」或从左侧点选设备再点画布。刷新后从 `GET /projects` + `GET /projects/{id}/workspace` 恢复最近的「工作台方案」。
2. 「校验并准备」。未通过时右栏给出原因，不会启动推演。
3. 「开始推演」。结果页四卡来自 `/simulation-jobs`。
4. 「估算成本并对比叉车加一」调用已有的价目、成本估算、再跑一版 DES，然后 `POST /comparisons`（`whole_solution`）。缺周期不补 0，雷达仅在接口 `radarEnabled` 时显示分数。
5. 「帮我生成布局」可选；采用后是新方案分支。quick 指标不是运营效率。
6. 右栏「尝试识别」仍是识图失败路径，不生成场地。

### 4. Worker

```bash
npm run worker:ping
```

## M5 范围（本切片）

| 项 | 行为 |
|---|---|
| DXF/矢量提取 | `DXF_EXTRACT_UNSUPPORTED`，底图保留，不写场地 |
| OCR | 高置信度仍是 `OCR_NOT_VERIFIED` / 待确认 |
| 多边形/高度分区 | 缺比例 `SCALE_MISSING`；复杂场地与简单矩形都不产出几何 |
| NSGA-II / 多目标 | 无候选，不宣称优于 `m2-plan-baseline-0.1` |
| 长期成本 | 数据齐全也是 `LIFECYCLE_NOT_IMPLEMENTED`，`horizonCost=null` |
| 扩容 / 运维轴 | `score=null`，不补 0 |
| 未校准自动化 | 不进入吞吐结论 |

## 与方案文档对照

- 权威：`04-总体与详细设计/`（UI-02 工作台，DEV-15/16，DEC-01 手动优先）
- 非生产：`03-UI原型` 演示公式
