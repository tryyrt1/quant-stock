# Session Handoff: 实时追踪功能开发失败并卸载 + 多项基础设施修复

**Date:** 2026-06-13 **Project:** quant-stock-pro **Session Duration:** ~6h

## Current State

**Task:** 盘中实时追踪功能已卸载，多项基础设施修复和前端改进已保留 **Phase:** 完成 **Progress:** 100%

## What We Did

尝试开发盘中实时追踪功能（盘前筛选候选股 + 盘中5分钟量增检测），但因数据源性能问题最终卸载。期间修复了多个底层问题，并添加了SEPA选股模式。

## Decisions Made

- **实时追踪功能卸载** — 腾讯K线API从云服务器频繁超时/WAF拦截，baostock并发查询挂起，导致筛选1000只股票需要10-20分钟，不可接受
- **板块热度合并到板块追踪页（保留）** — 不在tab栏单独显示，而是作为板块追踪页内的第二张卡
- **缓存轮换机制（保留）** — `_save_cache` 写入新数据前保留2份旧备份（.bak1, .bak2），`load_candidates` 依次尝试主文件→.bak1→.bak2
- **SEPA趋势模板 + Pivot突破（保留）** — 已加入 `patterns.py` 的 `ALL_PATTERNS` 列表和 `assess_patterns` 的看多信号

## Code Changes

**保留的改动：**

- `server.py` — `fetch_kline` 数据源改为 `ifzq.gtimg.cn`（原 `web.ifzq.gtimg.cn` 被WAF拦截），baostock作备用降级
- `engine/decision.py` — `assess_trend` 中新增SEPA趋势模板检查（price > MA50 > MA150 > MA200），`assess_patterns` 的bullish_keys 加入 `pivot_breakout`
- `engine/patterns.py` — 新增 `pattern_pivot_breakout`（突破前20日最高点+量比1.5倍），注册到 `ALL_PATTERNS`
- `static/index.html` — 板块热度卡合并进板块追踪页（`heatHistoryContainer`）

**已卸载的（代码已删除）：**
- `engine/intraday_tracker.py` — 整个文件删除
- `server.py` — intraday相关import、API路由、调度逻辑已移除
- `static/index.html` — 实时追踪tab和相关JS函数已移除

## 已卸载功能的参考信息（如需重新实现）

- 盘前筛选逻辑：`prefilter_candidates`（120日低位检查），最终跑通时300只→119只候选，耗时约10分钟
- 实时信号：`scan_candidates`（每5分钟，检测量增2倍+红实体+15日低位）
- 瓶颈点：腾讯API从云服务器超时（`timeout=8`经常触发），baostock多线程会挂起

## Known Issues

- [ ] 腾讯K线API `ifzq.gtimg.cn` 从云服务器有时可用有时超时，当前用baostock降级
- [ ] K线数据从本地桌面拉速度正常，从云服务器拉可能被限速

## Next Steps

1. [ ] 关注板块热度积累情况（需多日数据才能看到连续排行）
2. [ ] SEPA趋势模板和Pivot突破已加入评分体系，观察效果

## Files to Review on Resume

- `server.py:385` — `fetch_kline` 数据源（ifzq + baostock降级）
- `engine/decision.py:5` — `assess_trend` 含SEPA趋势模板
- `engine/patterns.py:11` — `pattern_pivot_breakout` 新形态
- `engine/patterns.py:835` — `ALL_PATTERNS` 列表含pivot_breakout
- `static/index.html` — 板块热度卡合并进板块追踪页
