# 2026-06-02 交班 — 周线选股策略

## 本次改动

### 1. 新建 `engine/weekly.py`
7 个周线分析函数：
- `check_ma20_trend()` — 20周线上翘 + 股价在其上
- `check_consecutive_up()` — 周连阳计数
- `check_volume_shrink_rise()` — 缩量上涨检测
- `check_engulfing()` — 周线阳包阴
- `check_consolidation()` — 长时间横盘
- `check_volume_harmony()` — 量价相关系数 0.3~0.7
- `assess_weekly()` — 综合评分 0-100 + 汇总文本

### 2. `server.py`
- `fetch_kline()` 新增 `period='week'` 参数
- `/api/weekly/{code}` — 个股周线分析端点
- `/api/scan/weekly` — 全市场周线扫描端点（前200只）
- `compute_daily_pick()` 追加周线信号分析

### 3. `static/index.html`
- 个股详情页新增"📅 周线分析"按钮 + 结果展示
- 选股模式 tab 自动加载周线扫描，"周线多头/周线阳包阴"排在最前面
- 每日一股底部显示周线状态

### 4. 涉及文件
- `engine/weekly.py` — **新建**
- `server.py` — fetch_kline 改造 + 新增端点
- `static/index.html` — 前端展示

## 未完成 / 已知问题
- 前端已部署但用户反馈部署未成功（已重新上传）
- 需要等 09:25 每日一股调度器运行后才能在每日一股中看到周线信息

## 部署
- 云服务器已部署，`sudo systemctl restart quant-stock`
- `git push` 待完成
