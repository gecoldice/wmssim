# next · 人工摆放切片

综合仓、常温、单层、标准托盘。客户自己摆放，准备布局，再看四张卡。这里没有自动规划、成本对比或识图。

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

界面打开就是 `template.mixed_wh_v0`：40 m × 24 m 综合仓，主路径设备已经按米摆好。工具条仍可改成空白场地或矩形模板（都不预放设备）。空白场地预填 40×24 m 和 3.5 m 通道，设备用目录默认长宽高。从元素库按住拖到画布，松手前看绿色可放、黄色注意、红色拒绝；货架和地堆没有通道接入点时放不下去。缩放只改变视野。决策页按本次运行的 `trajectory.segments` 插值移动资源。速度、处理时间和日出量默认是「未填写」；「填入测试工况」会写入夹具里的测试数，并标明不是项目默认值。

## 契约与金样

- Schema：`next/contracts/`
- 夹具：`next/fixtures/manual-wh/`
- 综合仓边占用 + 拆托接测（status 保持 spec_only）：`next/fixtures/mx/ACCEPTANCE_STEPS.md`
- 四卡核对：`next/fixtures/manual-wh/hand-check.md`
- 角色说明：`docs/slice-manual/`
