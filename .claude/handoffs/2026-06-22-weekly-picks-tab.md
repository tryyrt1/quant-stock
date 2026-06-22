# Session Handoff: 周线选股 Tab + 预测统计 Tab 替换

**Date:** 2026-06-22 **Project:** quant-stock-pro **Session Duration:** ~2h

## Current State

**Task:** 替换"预测统计"Tab 为"周线选股"Tab **Phase:** 阶段一完成，阶段二待实现 **Progress:** 60%

## What We Did

创建了全市场周线选股扫描脚本，替换了前端"预测统计"Tab 为"周线选股"Tab（上栏显示选中的 188 只股票），删除了服务器端预测统计相关代码。

## Decisions Made

- **创业板(3xx)应包含** — 用户纠正，之前错误排除了创业板
- **周均线基于周K线** — MA5/MA10/MA20 计算基于周K线收盘价，非日K线
- **成交量条件用均量趋势** — 严格逐周递增几乎不存在（0/200），改用"近3周均量>前3周均量×1.03"或"近3周至少2周量环比递增"
- **三条件同时满足筛选结果** — 量连增(39%)+周均线上(12%)+突破回调缩量(94%) → 全满足4.9%(188只)
- **预测统计后端全部删除** — 确认所有预测API/scheduler调用均独立，不影响其他功能
- **不上传 weekly_scanner.py 到服务器** — 扫描在本地运行，只上传 data/weekly_picks.json 结果文件

## Code Changes

**Files modified:**

- `weekly_scanner.py`（新） — 全市场周线扫描脚本，20并发50秒扫4690只，输出 data/weekly_picks.json
- `server.py` — 新增 `GET /api/weekly/picks` 端点；删除 `predict_intraday()`、`verify_intraday()` 函数；删除调度器中预测记录/验证/次日预测代码；删除 `/api/predictions/*` 全部8个API端点
- `static/index.html` — **只增加不删除**：新增 `#page-weekly-picks` 面板（上栏选股列表+下栏异动区域）；底部导航栏增加"📊 周线选股"按钮；`switchTab()` 增加 `page-weekly-picks` 行；增加 `loadWeeklyPicks()`/`renderWeeklyPicks()` 函数。原有预测统计Tab代码全保留未动

## Open Questions

- [ ] 下栏实时异动如何复用实时追踪Tab的联动数据

## Blockers / Issues

- 页面初始部署时因删除了预测JS导致所有JS异常，后改为只加不删解决

## Context to Remember

- 服务器 `APP_PASSWORD` 不等于本地的 `changeme`，登录验证在服务器用实际密码
- 服务器连接信息见本地 `~/.ssh/config` 和环境变量 `$CLOUD_HOST`
- 非交易时段API返回空列表，前端显示"暂无异动"
- 周线扫描不在服务器上运行，只在本地跑 `python weekly_scanner.py --upload`

## Next Steps

1. [ ] **阶段二：下栏实时异动** — 借鉴/复用 `static/index.html` 中 `loadIntradayMonitor()` 的 `fetchIntradayAlerts()` 代码（第1715行起），对周线选出的188只股票做实时监控，显示异动列表
2. [ ] 设置定时更新机制（crontab/任务计划程序）每周五收盘后自动扫描
3. [ ] 观察周线选出的188只股票实际表现，必要时调整筛选阈值

## Files to Review on Resume

- `weekly_scanner.py` — 全市场扫描脚本，选股逻辑在 `check_volume_increase()/check_ma_upward()/check_break_pullback()`
- `static/index.html:1656` — 周线选股每行 onclick 格式（`onclick='loadDetail("code","market")'`）
- `static/index.html:1715` — 阶段二复用参考：实时追踪Tab的 fetchIntradayAlerts() 代码
- `server.py` — 新增的 `/api/weekly/picks` 端点和删除的预测代码
