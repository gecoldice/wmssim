# simapp · 仓库布局规划与运营推演

工程根：`/Users/lovewinnie/wmssim/simapp`  
方案权威：`/Users/lovewinnie/wmssim/simulation`（尤其 `04-总体与详细设计/` v0.3）

**当前阶段：M4（成本/BOM 与多方案对比闭环）** — DEV-12–14。缺价显式 `missingItems`，不得参与「最低成本」排序；比较支持 `layout_only` / `whole_solution`；雷达缺轴不补零（共同轴 &lt;3 仅表格）；交付报告绑定历史 `layoutRevision` / `run`。

> M3 DES 仍为运营效率证据来源。M2 `evaluationLevel=quick` 仅为几何/路径估算。

## 版本口径

| 层 | 版本 |
|---|---|
| 外层对象（Project / Facility / Demand / CostEstimate / ComparisonSet / …） | `contractVersion = "0.3"` |
| 布局 Snapshot（推演只读） | `schemaVersion = "0.2"` |
| equip.json | `schema_version = "0.2"` |
| 派生器 | `derivationVersion = m1-derive-0.1` |
| 规划器 | `plannerVersion = m2-plan-baseline-0.1` |
| DES 引擎 | `engineVersion = m3-des-0.1` |
| 成本引擎 | `costEngineVersion = m4-cost-0.1` |
| 比较引擎 | `compareEngineVersion = m4-compare-0.1` |
| 指标定义 | `metricDefinitionVersion = metrics-m3-v1` |

坐标：平面米制，原点仓房西南角，**X 东 Y 北**；3D `(X,Y,Z)=(x, 高度, -y)`。  
**禁止**把 `03-UI原型` HTML 演示公式带进计算层。

## 目录

```text
simapp/
├── apps/web/                      # React 工作台（手动 / 规划 / DES / 成本对比）
├── services/api/                  # FastAPI：prepare / planning / simulation / cost / compare / reports
├── services/worker/               # 能力探测
├── contracts/
│   ├── schemas/v0.2/              # Snapshot + equip
│   ├── schemas/v0.3/              # 外层 + Cost/Comparison
│   └── openapi/openapi.yaml
├── packages/contracts-ts/
├── shared/python/
│   ├── simapp_contracts/
│   ├── simapp_units/
│   ├── simapp_geometry/
│   ├── simapp_derive/
│   ├── simapp_validate/
│   ├── simapp_plan/
│   ├── simapp_des/                # M3 DES
│   ├── simapp_cost/               # M4 BOM / CostEstimate / 最低成本推荐
│   └── simapp_compare/            # M4 ComparisonSet / 雷达 / 交付报告
├── fixtures/{valid,invalid}/
└── scripts/
    ├── validate_fixtures.py
    ├── run_m1_checks.py
    ├── run_m2_checks.py
    ├── run_m3_checks.py
    └── run_m4_checks.py
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

### 2. 校验 schema / 夹具 + M1–M4

```bash
source .venv/bin/activate
npm run validate:fixtures
npm run test:m1
npm run test:m2
npm run test:m3
npm run test:m4
```

### 3. API

```bash
source .venv/bin/activate
npm run dev:api
# → http://127.0.0.1:8000/api/v1/health  (milestone=M4, bomCost=true)
# → http://127.0.0.1:8000/docs
```

典型 M4 闭环：

```bash
# 1) prepare + simulation-jobs（历史 layoutRevision）
# 2) POST /price-books + POST /cost-bases
# 3) POST /cost-estimate-jobs
#    → status=incomplete 时 totals.total=null；eligibleForLowestCostRanking=false
# 4) POST /cost-ranking → 缺价候选排除，不宣称最低成本
# 5) POST /score-profiles + POST /comparisons
#    → mode=layout_only|whole_solution；雷达共同轴<3 仅表格
# 6) POST /reports → HTML 绑定 layoutRevision / runId / costEstimateId
```

### 4. 前端

```bash
npm run dev:web
# → http://127.0.0.1:5173
# 「M4：成本估算与多方案对比」
```

### 5. Worker 探测

```bash
npm run worker:ping
```

## M4 完成判据对照

| 项 | 结果 |
|---|---|
| DEV-12 BOM/成本 | 数量与布局一致；缺价 → `missingItems` + `knownSubtotal`；不给完整 `total` |
| 缺价不排最低成本 | `eligibleForLowestCostRanking=false`；`/cost-ranking` 排除 |
| DEV-13 比较 | `layout_only` 资源不一致 → 不可比；`whole_solution` 披露人数/成本 |
| 缺轴不补分 | 缺失 `score=null`；共同轴 &lt;3 → `radarEnabled=false` |
| 加入方案不改旧分 | ScoreProfile 锚点锁定；绝对分不随候选集漂移 |
| DEV-14 报告 | HTML 绑定历史 `layoutRevision` / `run`；不一致拒绝 |
| README + test:m4 | 本文件与 `npm run test:m4` |

## 夹具说明

目录见 `fixtures/meta/catalog.json`。M4 语义由 `npm run test:m4` 断言（缺价排序、复用/搬移分列、雷达、layout_only/whole_solution、报告版本一致、API e2e）。

## 与方案文档对照

- 权威：`04-总体与详细设计/`（流程、算法、契约 0.3、DEV/AC）
- 指标/成本/对比：`04/05`；UI-08；DEC-02/08/09
- 推演细则：`01/06`、`06b`、`07`、`12`
- 非生产：`03-UI原型` 演示公式
