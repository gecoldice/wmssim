# simapp · 仓库布局规划与运营推演

工程根：`/Users/lovewinnie/wmssim/simapp`  
方案权威：`/Users/lovewinnie/wmssim/simulation`（尤其 `04-总体与详细设计/` v0.3）

**当前阶段：M3（真实运营推演 DES）** — DEV-10–11。只读 Snapshot；确定性固定场景；库存守恒；通道图最短路；主四卡（吞吐/等待/利用率/瓶颈）由事件派生；回放绑定历史 `layoutRevision`。faultInject / skillTags 契约占位，忽略并告警。

> M2 `evaluationLevel=quick` 仍仅为几何/路径估算。M3 `detailed` DES 才可声称运营效率证据（本机引擎 `m3-des-0.1`）。

## 版本口径

| 层 | 版本 |
|---|---|
| 外层对象（Project / Facility / Demand / ValidationReport / …） | `contractVersion = "0.3"` |
| 布局 Snapshot（推演只读） | `schemaVersion = "0.2"` |
| equip.json | `schema_version = "0.2"` |
| 派生器 | `derivationVersion = m1-derive-0.1` |
| 规划器 | `plannerVersion = m2-plan-baseline-0.1` |
| DES 引擎 | `engineVersion = m3-des-0.1` |
| 指标定义 | `metricDefinitionVersion = metrics-m3-v1` |

坐标：平面米制，原点仓房西南角，**X 东 Y 北**；3D `(X,Y,Z)=(x, 高度, -y)`。  
**禁止**把 `03-UI原型` HTML 演示公式带进计算层。

## 目录

```text
simapp/
├── apps/web/                      # React 工作台（手动 / 规划 / DES）
├── services/api/                  # FastAPI：prepare / planning / simulation-jobs / runs
├── services/worker/               # 能力探测
├── contracts/
│   ├── schemas/v0.2/              # Snapshot + equip
│   ├── schemas/v0.3/              # 外层 + ValidationReport + PlanningRequest
│   └── openapi/openapi.yaml
├── packages/contracts-ts/
├── shared/python/
│   ├── simapp_contracts/
│   ├── simapp_units/
│   ├── simapp_geometry/
│   ├── simapp_derive/
│   ├── simapp_validate/
│   ├── simapp_plan/
│   └── simapp_des/                # M3：DES / 最短路 / 库存 / 四卡
├── fixtures/{valid,invalid}/
└── scripts/
    ├── validate_fixtures.py
    ├── run_m1_checks.py
    ├── run_m2_checks.py
    └── run_m3_checks.py
```

## 本地运行

### 1. 依赖

```bash
cd /Users/lovewinnie/wmssim/simapp
npm install
# 推荐 Python 3.11（本机 python3 若为 3.14，jsonschema/rpds-py 可能无轮子）
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r services/api/requirements.txt
```

### 2. 校验 schema / 夹具 + M1–M3

```bash
source .venv/bin/activate
npm run validate:fixtures
npm run test:m1
npm run test:m2
npm run test:m3
```

### 3. API

```bash
source .venv/bin/activate
npm run dev:api
# → http://127.0.0.1:8000/api/v1/health  (milestone=M3, des=true)
# → http://127.0.0.1:8000/docs
```

典型真实推演闭环：

```bash
# 1) 项目 + 场地 + 布局 revisions + variant
# 2) POST /layouts/{id}/prepare-jobs  → simulationReady=true
# 3) POST /demands + POST /operating-profiles
# 4) POST /simulation-jobs
#    → kpi 四卡 + kpiEvidence（可追 outbound 事件）
#    → trajectory.layoutRevision = 历史准备修订
#    → GET /runs/{runId} 回放同一绑定
```

未 prepare / revision 不一致 → `NOT_SIMULATION_READY` / `LAYOUT_REVISION_MISMATCH`。

### 4. 前端

```bash
npm run dev:web
# → http://127.0.0.1:5173
# 「M3：prepare 后真实推演」
```

### 5. Worker 探测

```bash
npm run worker:ping
```

## M3 完成判据对照

| 项 | 结果 |
|---|---|
| DEV-10 DES 核心 | 只读 Snapshot；FIFO+空闲最久；边容量等待；库存守恒；RunManifest |
| 固定场景可复现 | 同快照/场景/种子/引擎版本 → 同 KPI/事件序/轨迹段数 |
| DEV-11 四卡与回放 | 吞吐/等待/利用率/瓶颈；`kpiEvidence` 追 outbound 事件；轨迹绑历史 layoutRevision |
| 占位能力 | faultInject enabled → 忽略告警；skillTags → 忽略告警 |
| 门禁 | 须 M1 prepare / simulationReady |
| README + test:m3 | 本文件与 `npm run test:m3` |

## 夹具说明

目录见 `fixtures/meta/catalog.json`。M3 语义由 `npm run test:m3` 断言（可复现、守恒、证据链、回放绑定、未 prepare 拒绝、零需求不伪造等待）。

## 与方案文档对照

- 权威：`04-总体与详细设计/`（流程、算法、契约 0.3、DEV/AC）
- 推演细则：`01/06`、`06b`、`07`、`12`
- 兼容：`01/08`、`12`（Snapshot/equip 0.2）
- 非生产：`03-UI原型` 演示公式
