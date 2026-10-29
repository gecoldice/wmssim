# simapp · 仓库布局规划与运营推演

工程根：`/Users/lovewinnie/wmssim/simapp`  
方案权威：`/Users/lovewinnie/wmssim/simulation`（尤其 `04-总体与详细设计/` v0.3）

**当前阶段：M2（可选自动规划）** — DEV-06–09。场地确认门禁；规划向导与 PlanningJob；DEC-05 基线规划器（常温单层标准托盘）；候选采用=新方案分支；局部重排与锁定；乐观锁并发不覆盖。手动路径（M1）仍独立可用。

> M2 `evaluationLevel=quick` 仅几何容量/通道路径估算，**不得宣称已验证运营效率**（待 M3 DES）。

## 版本口径

| 层 | 版本 |
|---|---|
| 外层对象（Project / Facility / Demand / ValidationReport / …） | `contractVersion = "0.3"` |
| 布局 Snapshot（推演只读） | `schemaVersion = "0.2"` |
| equip.json | `schema_version = "0.2"` |
| 派生器 | `derivationVersion = m1-derive-0.1` |
| 规划器 | `plannerVersion = m2-plan-baseline-0.1` |

坐标：平面米制，原点仓房西南角，**X 东 Y 北**；3D `(X,Y,Z)=(x, 高度, -y)`。  
**禁止**把 `03-UI原型` HTML 演示公式带进计算层；金样 KPI 待 M3 引擎后再锁定。

## 目录

```text
simapp/
├── apps/web/                      # React 工作台（手动 + 可选规划采用）
├── services/api/                  # FastAPI：场地/规划任务/候选采用/prepare
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
│   └── simapp_plan/               # M2：确认门禁 / 基线规划 / 锁定 / 采用
├── fixtures/{valid,invalid}/
└── scripts/
    ├── validate_fixtures.py
    ├── run_m1_checks.py
    └── run_m2_checks.py
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

### 2. 校验 schema / 夹具 + M1/M2 语义

```bash
source .venv/bin/activate
npm run validate:fixtures
npm run test:m1
npm run test:m2
```

### 3. API

```bash
source .venv/bin/activate
npm run dev:api
# → http://127.0.0.1:8000/api/v1/health  (milestone=M2, planning=true)
# → http://127.0.0.1:8000/docs
```

典型可选规划闭环：

```bash
# 1) 建项目 + 确认场地（evidence.confirmationStatus=confirmed，单位 m）
# 2) POST /api/v1/demands
# 3) 可选：POST /projects/{id}/planning-drafts（关闭重开不丢；缺数据目标禁用原因可见）
# 4) POST /api/v1/planning-jobs  → candidates（真实 ST-PAL-01 可编辑布局）
# 5) POST /api/v1/candidates/{id}/adoptions
#    → 新 Variant 分支；陈旧 revision → 409 REVISION_CONFLICT
```

手动路径仍走 `POST /layouts/{id}/revisions` → `prepare-jobs`，**不依赖**规划。

### 4. 前端

```bash
npm run dev:web
# → http://127.0.0.1:5173
# 「手动路径：保存并推演准备」与「可选规划：生成并采用分支」
```

### 5. Worker 探测

```bash
npm run worker:ping
```

## M2 完成判据对照

| 项 | 结果 |
|---|---|
| DEV-06 场地确认 | 未确认 / 未标定 → `INPUT_UNCONFIRMED`；不可产出 validated 候选 |
| DEV-07 向导/任务 | planning-drafts；PlanningJob；缺效率/成本目标禁用原因可见 |
| DEV-08 规划器基线 | DEC-05 模板枚举；真实 ST-PAL-01；派生校验通过；搜索终止可解释 |
| DEV-09 采用与局部重排 | 采用=新分支；锁定/区域外不变；`REVISION_CONFLICT` 不覆盖 |
| 手动独立 | `capabilities.manualLayout=true`；prepare 路径不变 |
| 无运营效率宣称 | `claimsOperationalEfficiency=false`；detailed → unsupported |

## 夹具说明

目录见 `fixtures/meta/catalog.json`。M2 语义由 `npm run test:m2` 断言（未确认场地、基线候选、锁定局部重排、采用冲突、detailed 拒绝）。

## 与方案文档对照

- 权威：`04-总体与详细设计/`（流程、算法 A0–A8、契约 0.3、DEV/AC）
- 兼容：`01/08`、`12`（Snapshot/equip 0.2）
- 非生产：`03-UI原型` 演示公式
