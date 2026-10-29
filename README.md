# simapp · 仓库布局规划与运营推演

工程根：`/Users/lovewinnie/wmssim/simapp`  
方案权威：`/Users/lovewinnie/wmssim/simulation`（尤其 `04-总体与详细设计/` v0.3）  
远程：本机没有可用的 `gh` 登录，仓库仍无 `origin`。

**当前阶段：M5 切片（工作台 + 扩展失败路径）** — 在 M1–M4 之上。

- 工作台：左元素库 / 中画布 / 右参数。手动摆放 → 保存 → 校验并准备 → 跑 DES → 四卡。可选「帮我生成布局」。
- 四卡、库容和成本只显示接口结果。不使用 `03-UI原型` 的演示公式。
- DEV-15 识图（DXF / OCR / 多边形分区）与 DEV-16（NSGA-II、多目标、长期成本、扩容/运维量表、未校准自动化）**只返回失败或不支持**，不生成几何、分数或收益。

> M3 DES 仍是运营效率证据。M2 `evaluationLevel=quick` 只是几何/路径估算。M4 缺价不排最低成本，缺轴不补分。

## 版本口径

| 层 | 版本 |
|---|---|
| 外层对象 | `contractVersion = "0.3"` |
| 布局 Snapshot | `schemaVersion = "0.2"` |
| equip.json | `schema_version = "0.2"` |
| 派生器 | `derivationVersion = m1-derive-0.1` |
| 规划器 | `plannerVersion = m2-plan-baseline-0.1` |
| DES 引擎 | `engineVersion = m3-des-0.1` |
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
└── scripts/run_m1_checks.py … run_m5_checks.py
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
npm run build:web
```

### 3. API 与工作台

```bash
source .venv/bin/activate
npm run dev:api
# 另一个终端
npm run dev:web
```

- API：http://127.0.0.1:8000/api/v1/health （`milestone=M5`，识图/NSGA-II/长期成本为 false）
- 工作台：http://127.0.0.1:5173

主路径：

1. 「使用矩形模板」或从左侧点选设备再点画布。
2. 「校验并准备」。未通过时右栏给出原因，不会启动推演。
3. 「开始推演」。结果页四卡来自 `/simulation-jobs`。
4. 「帮我生成布局」可选；采用后是新方案分支。quick 指标不是运营效率。
5. 右栏「尝试识别」与「方案对比 → 探测不支持项」展示 M5 失败路径。

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
