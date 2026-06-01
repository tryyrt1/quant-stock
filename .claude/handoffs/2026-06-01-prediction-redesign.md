# 2026-06-01 交班 — 预测系统重构

## 本次改动

### 1. 预测系统全面重构
- **去除**原有全市场信号准确率统计、多方法矩阵、自动诊断等
- **替换为**自选股走势预测（盘中形态）+ 次日方向预测

### 2. 后端
- `server.py`:
  - `predict_intraday(wl, quotes)` — 09:25 调度器调用，用 make_decision + 跳空预测形态
  - `verify_intraday()` — 15:01 用当日 K 线 OHLC 验证形态对错
  - `/api/watchlist/predict` — 改为读 intraday.json 缓存（不再实时拉行情）
  - 调度器 09:25 → predict_intraday, 15:01 → verify_intraday + nextday 记录
- `engine/prediction_tracker.py`:
  - `record_nextday_prediction()` — 收盘后记录次日方向
  - `verify_nextday_predictions()` — 次日验证
  - `get_nextday_stats()` — 历史准确率统计

### 3. 前端
- `static/index.html`:
  - 预测统计页重写，显示自选股形态预测 + 验证结果 + 次日方向
  - 去除原有的 5 秒自动刷新（预测全天锁定不再需要）
  - 去除 renderMethodMatrix/renderMethodBreakdown/renderPredictionStats

### 4. 涉及文件
- `server.py` — 核心改动
- `engine/prediction_tracker.py` — 新函数
- `static/index.html` — 前端简化

## 未完成/已知问题
- 今日形态预测和次日预测都要等调度器触发后才生成（09:25 / 15:01）
- `nextday.json` 刚部署为空，需 15:01 后才有数据
- 云服务器 prediction_tracker.py 可能仍为旧版，已重新上传

## 部署
- 云服务器已部署，`sudo systemctl restart quant-stock`
