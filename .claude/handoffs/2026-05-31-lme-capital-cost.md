# 2026-05-31 会话交班

## 本次改动

### 1. LME 伦敦金属行情
- `server.py`: COMMODITIES 新增 6 个 LME 品种（伦铜/铝/锌/镍/铅/锡）
- `fetch_commodity_kline` 新增 `type='lme'` 分支，调用 `futures_global_spot_em()` 获取实时行情
- `commodity_detail` 响应含 `lme_stock`（LME 仓单库存数据）
- `static/index.html`: 新增 LME 库存卡片展示

### 2. 主力成本多周期参考
- `stock_capital_api`: kline 从 60→250 天
- 新增 MA60/MA120/MA250 均线参考成本 + VWAP 全周期加权均价
- 前端主力成本面板新增"多周期参考成本"表格

### 3. Bug 修复
- `_int()` 函数使用 `int(float(v))` 替代 `int(v)`，修复腾讯 API 成交量解析（返回"2366340.000"浮点字符串导致全量返回 0）
- `static/index.html`: commodityGrid max-height 从 160px→220px，添加 no-cache meta 标签
- `server.py`: index 路由添加 Cache-Control 响应头

### 4. 涉及文件
- `server.py` — LME 品种、主力成本周期、_int 修复
- `static/index.html` — LME/MA 显示、缓存控制

## 未完成 / 已知问题
- 东方财富个股 API (`stock_individual_info_em`) 连接被拒，同花顺/雪球等外部主力成本数据源未就绪
- 洛阳钼业（603993）主力建仓痕迹（放量上涨日）检测无结果，可能因 250 日线数据包含大范围价格波动

## 部署
- 云服务器 159.75.103.100 已部署，`sudo systemctl restart quant-stock`
