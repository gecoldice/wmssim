# simapp · 仓库布局规划与运营推演

工程根：`/Users/lovewinnie/wmssim/simapp`  
方案权威：`/Users/lovewinnie/wmssim/simulation`（尤其 `04-总体与详细设计/` v0.3）

**当前阶段：M1（手动布局路径）** — DEV-04–05。项目/工作台/layoutRevision；派生货位·通道·accessNode；权威校验（碰撞/窄通道/跨墙）；可保存「推演准备」状态。手动路径**不依赖**自动规划（M2）。

## 版本口径

| 层 | 版本 |
|---|---|
| 外层对象（Project / Facility / Demand / ValidationReport / …） | `contractVersion = "0.3"` |
| 布局 Snapshot（推演只读） | `schemaVersion = "0.2"` |
| equip.json | `schema_version = "0.2"` |
| 派生器 | `derivationVersion = m1-derive-0.1` |

坐标：平面米制，原点仓房西南角，**X 东 Y 北**；3D `(X,Y,Z)=(x, 高度, -y)`。  
**禁止**把 `03-UI原型` HTML 演示公式带进计算层；金样 KPI 待 M3 引擎后再锁定。

## 目录

```text
simapp/
├── apps/web/                      # React 工作台（手动保存→推演准备）
├── services/api/                  # FastAPI：项目/布局修订/prepare-jobs
├── services/worker/               # 能力探测（派生/校验由 API 同进程调用）
├── contracts/
│   ├── schemas/v0.2/              # Snapshot + equip
│   ├── schemas/v0.3/              # 外层 + ValidationReport
│   └── openapi/openapi.yaml
├── packages/contracts-ts/
├── shared/python/
│   ├── simapp_contracts/
│   ├── simapp_units/
│   ├── simapp_geometry/           # AABB / 线段 / 障碍
│   ├── simapp_derive/             # LayoutDocument → Snapshot
│   └── simapp_validate/           # ValidationReport
├── fixtures/{valid,invalid}/
└── scripts/
    ├── validate_fixtures.py
    └── run_m1_checks.py
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

### 2. 校验 schema / 夹具 + M1 语义

```bash
source .venv/bin/activate
PYTHONPATH=shared/python python3 scripts/validate_fixtures.py
PYTHONPATH=shared/python python3 scripts/run_m1_checks.py
# 或
npm run validate:fixtures
npm run test:m1
```

### 3. API（手动路径）

```bash
source .venv/bin/activate
npm run dev:api
# → http://127.0.0.1:8000/api/v1/health
# → http://127.0.0.1:8000/docs
```

典型手动闭环（不经规划）：

```bash
# 1) 建项目
curl -s -X POST http://127.0.0.1:8000/api/v1/projects \
  -H 'Content-Type: application/json' \
  -d '{"name":"demo","unitSystem":"metric"}'

# 2) 写入场地修订（用 fixtures/valid/fx01-small-rect-facility.json）
# 3) POST /api/v1/layouts/{layoutId}/revisions 保存布局（prepareStatus=saved）
# 4) POST /api/v1/layouts/{layoutId}/prepare-jobs
#    → simulationReady=true 时即为「推演准备」
```

### 4. 前端

```bash
npm run dev:web
# → http://127.0.0.1:5173 （/api 代理到 8000）
# 按钮「手动路径：保存并推演准备」走完整 DEV-04/05 闭环
```

### 5. Worker 探测

```bash
npm run worker:ping
```

## M1 完成判据对照

| 项 | 结果 |
|---|---|
| 项目 / 工作台 / layoutRevision | API 内存存储；修订乐观锁；保存 ≠ 可推演 |
| 推演准备 | `prepare-jobs` 派生 + 校验；`simulationReady` 仅 status=pass |
| 碰撞 | FX-M1-COLLISION → `GEOMETRY_INVALID` |
| 窄通道 | FX-M1-NARROW → `NARROW_AISLE`（相对设备声明 `minClearWidthM`，非编造消防阈值） |
| 跨墙 | FX-M1-CROSS-WALL / SNAP → `NO_ACCESS_NODE`；不生成穿墙边 |
| 独立于 M2 | health.capabilities.planning=false |

## 夹具说明

目录见 `fixtures/meta/catalog.json`。`expect` 管 schema/轻语义；`prepareExpect` 由 `npm run test:m1` 断言。

## 与方案文档对照

- 契约：`simulation/04-总体与详细设计/06-数据模型与接口契约.md`
- 任务：`04/.../07-Cursor实施任务与验收.md` DEV-04–05 / AC-01 / AC-17 / FX-02 性质
- Snapshot/equip：`01-方案正文/08`、`12`
