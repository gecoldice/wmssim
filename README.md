# simapp · 仓库布局规划与运营推演

工程根：`/Users/lovewinnie/wmssim/simapp`  
方案权威：`/Users/lovewinnie/wmssim/Simulation`（尤其 `04-总体与详细设计/` v0.3）

**当前阶段：M0（契约与夹具）** — DEV-01–03。本地可跑脚手架、校验 JSON Schema / 夹具；尚无 DES / 规划计算。

## 版本口径

| 层 | 版本 |
|---|---|
| 外层对象（Project / Facility / Demand / PlanningRequest / …） | `contractVersion = "0.3"` |
| 布局 Snapshot（推演只读） | `schemaVersion = "0.2"` |
| equip.json | `schema_version = "0.2"` |

坐标：平面米制，原点仓房西南角，**X 东 Y 北**；3D `(X,Y,Z)=(x, 高度, -y)`。  
**禁止**把 `03-UI原型` HTML 演示公式带进计算层；金样 KPI 待 M3 引擎后再锁定，夹具不含猜测 KPI。

## 目录

```text
simapp/
├── apps/web/                 # React + TypeScript (Vite)
├── services/api/             # FastAPI 骨架
├── services/worker/          # 计算 worker 骨架（无业务循环）
├── contracts/
│   ├── schemas/v0.2/         # Snapshot + equip
│   ├── schemas/v0.3/         # 外层对象
│   └── openapi/openapi.yaml
├── packages/contracts-ts/    # TS 类型（与 schema 同源手维，后续可生成）
├── shared/python/            # simapp_contracts / simapp_units
├── fixtures/{valid,invalid}/ # 正反例夹具
└── scripts/validate_fixtures.py
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

### 2. 校验 schema / 夹具

```bash
source .venv/bin/activate
PYTHONPATH=shared/python python3 scripts/validate_fixtures.py
# 或
npm run validate:fixtures
```

### 3. API

```bash
source .venv/bin/activate
npm run dev:api
# → http://127.0.0.1:8000/api/v1/health
# → http://127.0.0.1:8000/docs
```

### 4. 前端

```bash
npm run dev:web
# → http://127.0.0.1:5173 （/api 代理到 8000）
```

### 5. Worker 探测

```bash
npm run worker:ping
```

## 夹具说明

目录见 `fixtures/meta/catalog.json`。`expect=pass` 须 schema+语义通过；`fail` 须 schema 拒绝；`semantic_fail` 须 schema 通过但语义拒绝（如缺 `accessNodeId`）。

FX-01：小矩形场地 + 连通通道图 + ST-PAL-01 盒子代理。  
FX-07：零需求结构合法夹具（**无 KPI 期望值**）。

## 与方案文档对照

- 契约：`Simulation/04-总体与详细设计/06-数据模型与接口契约.md`
- Snapshot/equip：`01-方案正文/08`、`12` + `00-工作区原稿/equip-schema-v0.2.json`
- 任务：`04/.../07-Cursor实施任务与验收.md` DEV-01–03 / FX-01…
