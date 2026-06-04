# 2026-05-26 多方法预测 + 多时间维度自动回测

## 实现内容

### 新增功能：多方法独立预测
原有的6个评估维度（趋势/形态/价位/量能/板块/分时）现在各自独立输出信号（买入/增持/持有/减仓/卖出），不再只有综合加权结果。存储在预测记录的 `methods` 字段中。

### 文件变更

**`engine/decision.py`**
- 新增 `score_to_signal(score)` 函数 — 将0-100分数映射为买卖信号
- `make_decision()` 增加 `method_signals` 返回值（6个维度的独立信号）
- 信号映射改用 `score_to_signal()`，不再用内联 if/elif

**`engine/prediction_tracker.py`**
- `record_prediction()` 增加 `methods=None` 可选参数，有值时存入 `record["methods"]`
- `verify_predictions()` 验证主记录后，遍历 `record.get("methods",{})` 用相同 `change_pct` 验证各方法
- 增加 `same_day_change_pct` 字段——存储当日（分时）涨跌幅（预测价→当日收盘价）
- 新增 `get_method_multi_offset_stats()` — 各方法在偏移[0(当日),1,2,3,5,10,15,20,30]日的准确率
- 新增 `get_stock_method_snapshot(code)` — 个股最新记录的methods快照
- `get_recent_results()` 输出的records增加 `methods` 字段

**`server.py`**
- import 增加 `get_method_multi_offset_stats`, `get_stock_method_snapshot`
- 调度器 `_run_scheduled_scans()` 中 `record_prediction()` 调用增加 `methods=decision.get('method_signals', {})`
- 新增 `GET /api/predictions/methods/stats`
- 新增 `GET /api/predictions/methods/<code>`

**`static/index.html`**
- 移除 `renderStockChart()` 函数（个股曲线小图）
- 移除记录下方的SVG曲线调用
- 新增 `renderMethodMatrix()` — 多方法对比矩阵表，列最佳值高亮，按+1日胜率排序，含综合法基线
- 新增 `renderMethodBreakdown()` — 每条记录下方显示各方法信号分解行
- 个股详情页决策面板增加方法信号展示
- `loadPredictions()` 增加 `methodStats` 数据获取

### 已知状态
- 云服务器（159.75.103.100）已部署新代码并重启
- 手动生成了10只股票的预测记录（含methods数据，record_time='15:10'）
- 这些记录尚未验证（需要明天15:10后或手动触发verify）
- 方法对比矩阵需待验证后才有数据

### 历史持仓信息（用户提供）
- 洛阳钼业(603993) 1/4仓位，明日(5/27)除权除息，每股分红0.286元
- 今日(5/26)大涨5.43%收20.39元，登记日抢权行情
