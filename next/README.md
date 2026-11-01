# next · 人工摆放切片

综合仓、常温、单层、标准托盘。客户自己摆放，准备布局，再看四张卡。叉车台数可以按等待均值搜索。这里没有成本对比或识图。

旧的 `apps/`、`services/`、`shared/` 保持原样。新代码只在本目录。

## 本地运行

```bash
python3 -m pip install -r next/requirements.txt
PYTHONPATH=next python3 next/scripts/accept_slice.py
PYTHONPATH=next python3 -m uvicorn api.app.main:app --app-dir next --host 127.0.0.1 --port 8090
```

另一个终端：

```bash
cd next/web
npm install
npm run dev
```

浏览器打开 Vite 提示的地址。开发服务器把 `/api` 转到 `127.0.0.1:8090`。

界面打开就是 `template.mixed_wh_v0`：40 m × 24 m 综合仓，主路径设备已经按米摆好。工具条仍可改成空白场地或矩形模板（都不预放设备）。空白场地预填 40×24 m 和 3.5 m 通道，设备用目录默认长宽高。从元素库按住拖到画布，松手前看绿色可放、黄色注意、红色拒绝；货架和地堆没有通道接入点时放不下去。缩放只改变视野。决策页按本次运行的 `trajectory.segments` 插值移动资源。速度、处理时间和日出量默认是「未填写」；「填入测试工况」会写入夹具里的测试数，并标明不是项目默认值。勾选小件分拣后要填拣货人数、拣选时间和拣选箱数；和拆托一起开时还要填每托箱数。拣货人把箱送到包装台，箱数不进托盘吞吐。弯道、合流、分流、缓冲和直线一样要接上端口才能推演。合流固定同时一托。缓冲默认 1 位，可以改。垂直、滑槽、环线和诱导口仍然拒绝。通道可以勾成单向，也可以加一个折点。转向半径留空不判断转弯。AGV 数量留空不带车；填了数量也只是多一队车，整托仍由叉车走。立体库要填节拍，留空不能推演。节拍只计取一托的时间。准备通过后可以按等待均值找最少叉车，结果留在编辑页，可以把台数写回叉车数量。叉车、拣货人和 AGV 的单价留空不算合计；这次运行里有人开车却没填单价时，不算合计，也不比哪一次更省。推演完成后，「仿真报告」只转写这一次运行的四卡。可以记下这组四卡，再和下一次运行相减。利用率缺一侧不写成 0。台数不同会写明差不能全部算到布局上。改这些单价不把四卡标成过期。

## 契约与金样

- Schema：`next/contracts/`
- 夹具：`next/fixtures/manual-wh/`
- 综合仓边占用 + 拆托接测（status 保持 spec_only）：`next/fixtures/mx/ACCEPTANCE_STEPS.md`
- 四卡核对：`next/fixtures/manual-wh/hand-check.md`
- 小件人路径金样：`next/fixtures/gold/G-PICK-01.json`、`G-PICK-02.json`
- 单向与转向金样：`next/fixtures/gold/G-WAY-01.json`、`G-WAY-02.json`、`G-TURN-01.json`、`G-TURN-02.json`
- AGV 金样：`next/fixtures/gold/G-AGV-01.json`、`G-AGV-02.json`
- 立体库金样：`next/fixtures/gold/G-ASRS-01.json`、`G-ASRS-02.json`
- 叉车台数搜索：`next/fixtures/plan/G-PLAN-01.json` 至 `G-PLAN-04.json`。只按等待均值找最少台数，不含价格。
- 输送拓扑金样（仍 `spec_only`）：`next/fixtures/conveyor/G-CV-04.json` 至 `G-CV-07.json`
- 角色说明：`docs/slice-manual/`
