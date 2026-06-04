# 2026-06-04 交班 — 周线扩充 + 密码保护 + 多项优化

## 本次改动

### 1. 周线分析方法大扩充
- `engine/weekly.py` 新增 6 个函数：
  - `check_weekly_macd()` — MACD金叉/二次金叉/零轴上方
  - `check_ma10_trend()` — 10周均线趋势
  - `check_bullish_alignment()` — 5>10>20>30多头排列
  - `check_rsi_divergence()` — RSI超买超卖+底背离
  - `check_volume_stack()` — 堆量+立桩量
  - `check_macd_ma_resonance()` — MACD+均线共振
- `assess_weekly()` 集成 r8-r13
- 前端周线分析卡片新增 9 行状态显示

### 2. 选股模式新形态
- 新增：周线金叉、周线二次金叉、周线底背离、周线放量突破
- 全市场扫描扩大到 500 只

### 3. 密码保护
- Flask session + 登录页面
- 密码 `ga192336` 存在服务器环境变量 `APP_PASSWORD`，不在代码中
- 首次访问显示登录页，登录后存入 session

### 4. 其他优化
- 深度分析保持时间从 30 秒改为 3.5 分钟
- 选股模式结果切换 tab 不丢失（state.patterns 缓存）
- 每日一股 + 全市场扫描显示扫描计数

### 5. 涉及文件
- `engine/weekly.py` — 6 新函数
- `server.py` — 密码、500只、扫描计数
- `static/index.html` — 周线展示、3.5分钟、缓存、计数

### 6. 已知问题
- 密码 session 依赖 `secret_key`，重启后需重新登录
- `scanned_count` 需下次 09:25/15:01 计算后写入缓存才显示实际值（默认为 500）

## 部署
- 云服务器已部署
