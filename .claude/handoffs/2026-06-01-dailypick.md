# 2026-06-01 会话交班 — 每日一股

## 本次改动

### 1. 每日一股功能
- 首页底部"分析报告" tab 替换为"⭐每日一股"
- **09:25 自动推荐**今日必涨股，**15:01 自动推荐**明日必涨股
- 全市场扫描：取 400 只候选股，7 方法决策引擎评分，排除涨停
- 缓存到 `data/dailypick.json`，推荐全天锁定不变

### 2. 后端
- `server.py`:
  - `compute_daily_pick(period)` — 全市场扫描决策函数
  - `/api/dailypick` — 返回缓存推荐结果，过期自动后台计算
  - `get_dailypick_period()` — 时间段判断逻辑
  - `SCHEDULE_TIMES` 新增 `(15,1)` 时间点
  - `_run_scheduled_scans()` 新增 (9,25) 和 (15,1) 触发计算

### 3. 前端
- `static/index.html`:
  - tab 改为"⭐每日一股"，触发 `loadDailyPick()`
  - 新增 `page-dailypick` 容器
  - `loadDailyPick()` / `renderDailyPick()` — 完整推荐卡渲染
  - 显示：时段标记、股票头部、信号徽章、7维度评分条、形态、理由、S/R、风险

### 4. 涉及文件
- `server.py` — 核心逻辑 + API + 调度器
- `static/index.html` — 前端 tab + 渲染

## 未完成 / 已知问题
- `all_stocks.json` 本地文件 encoding 问题（某些股票名含非UTF-8字符）
- 推荐股票价格可能偏低（如 3.87 元），后续可加价格过滤
- 首日部署后需等待 09:25 或 15:01 定时计算，或首次访问 API 触发异步计算

## 部署
- 云服务器 159.75.103.100 已部署，`sudo systemctl restart quant-stock`
