# wmssim

仓库布局与运营推演。产品主线在 `next/`：综合仓、常温、单层、标准托盘。自己摆放，准备布局，再看这一次运行的四张卡。

`main` 上的代码就是原先 `cursor/m5-workbench-ui-5ace` 那一棵树。其余功能分支是这条线 squash 合并之前的提交，文件内容已经在这里，不要再把那些分支 merge 回来，否则会用旧文件覆盖后来的输送、模型库和七类元素库。

坐标：平面米，原点在场地西南角，X 东 Y 北。3D 为 `(x, 高度, -y)`。

## 本地运行

```bash
python3 -m pip install -r next/requirements.txt
PYTHONPATH=next python3 next/scripts/accept_slice.py
PYTHONPATH=next python3 next/scripts/run_cv.py
PYTHONPATH=next python3 -m uvicorn api.app.main:app --app-dir next --host 127.0.0.1 --port 8090
```

另一个终端：

```bash
cd next/web
npm install
npm run dev
```

开发服务器把 `/api` 转到 `127.0.0.1:8090`。界面细节见 `next/README.md`。

## 这条主线已经有的

人工摆放、服务端修订号、准备校验（跨墙、窄通道、出界、重叠、无路）、整托叉车、拆托、小件人路径、通道边占用、输送（直线、弯道、合流、分流、缓冲）、四卡与本次轨迹回放、78 个可放置类型、11 个 P0 模型。

综合仓 `MX-D*` 和输送 `G-CV-*` 的脚本可以断言通过，夹具状态仍是 `spec_only`。断言通过不等于业务验收通过。

## 接下来按这个顺序做

每一刀单独金样，做完再开下一刀。不要在一个改动里把下面各项都做成能点的按钮。

1. 小件人路径已有金样 `G-PICK-01`（连续两箱）和 `G-PICK-02`（拆托后把箱送到包装台）。`generate_only` 仍只留骨架。综合仓三流夹具保持 `spec_only`。
2. 弯道、合流、分流、缓冲已按长度除以速度走。合流同时只过一托。分流只走去向那条支路。缓冲要填位数，满了就等。金样 `G-CV-04` 到 `G-CV-07` 仍是 `spec_only`。垂直、滑槽、环线、诱导口继续拒绝。
3. 转向半径和单向通道已有金样。直角弯要求通道宽至少是半径的 2 倍。单向只沿中心线方向走，逆行在进调度前拒绝。
4. `MH-AGV-01` 已能沿通道走。任务写 `carrier: agv` 时用这台车的空驶和载货速度。没有 AGV 资源就在进调度前拒绝。只把图标摆上、任务仍由叉车做时，不改叉车结果。充电点和等待点仍拒绝。
5. `ST-ASRS-01` 已按节拍取一托。节拍留空就在进调度前拒绝。填了节拍也不把叉车开进货位，旁边的普通货位仍按通道走。
6. 叉车台数可以按等待均值搜索：同一条通道上两托同时就绪，一台时第二托等 20 秒，均值 10；两台且边容量为 2 时等待为 0。目标是均值不超过 0，所以停在 2 台。加到上限仍等不及就拒绝。这不是报价，也不是多方案布局对比。成本、方案对比和报告仍不做，也不搬演示价。
7. 识图（DXF / OCR / 多边形）和 NSGA-II、长期成本。在有真实模型和验收之前，继续明确返回不支持，不补假结果。
8. 其余设备的 GLB。没有模型源就继续用代理盒。
9. 项目级授权可以单做技术切片。5 人易用性小样不是代码任务。

仍会拒绝推演、只允许摆位置的类型，以 `next/des/scope.py` 为准。

## 旧树

`apps/`、`services/`、`shared/` 是 2026-10-29 决定停用的拼装线（M1–M5）。代码还在，方便对照，不是当前产品。本地跑旧线：

```bash
npm install
python3 -m pip install -r services/api/requirements.txt
npm run validate:fixtures
npm run test:m1 && npm run test:m2 && npm run test:m3 && npm run test:m4 && npm run test:m5
npm run dev:api    # 127.0.0.1:8000
npm run dev:web    # 127.0.0.1:5173
```

旧工作台的识图和多目标入口固定返回失败。不要在那条线上继续加功能。
