# Session Handoff: 资金流全删 + 板块热度记录 + Tab替换

**Date:** 2026-06-11 **Project:** quant-stock-pro **Session Duration:** ~3h

## Current State

**Task:** 删除全部资金流维度 + 板块热度记录追踪替换宏观/商品Tab **Phase:** 已部署 **Progress:** 100%

## What We Did

1. **彻底删除资金流** — decision.py中删除assess_capital_flow/权重/详情；ml_scorer移除capital维度；server.py中删除资金流引用。评分从7维→6维，capital权重分摊给trend/patterns/sector等
2. **板块热度记录** — 调度器每次板块扫描后记录前30名板块名称到sector_heat.json；新增/api/sectors/heat-history接口
3. **替换宏观/商品Tab** — 删除commodity页，新增"板块热度"Tab，显示近5日进前30次数排行
4. **板块追踪扩展到30** — fetch_hot_boards处理全部概念板块，sectors_hot_api优先读缓存不足时实时补扫
5. **PREDEFINED扩展到30个**

## Decisions Made

- **热度记录每天只保留最后一次扫描结果** — 盘中多次扫描更新当日记录，15:10收盘版本为定版
- **板块追踪改为读缓存** — 避免每次请求实时扫描超时

## Code Changes

**Modified:**
- `engine/decision.py` — 删除capital函数/权重/详情引用 (line 433, 619, 628, 638, 657, 664, 701)
- `engine/ml_scorer.py` — 移除capital维度 (line 28, 90)
- `engine/sectors.py` — PREDEFINED从8扩到30；fetch_hot_boards处理全部候选 (line 4, 440-441)
- `server.py` — 调度器加热度记录(3156行附近)；新增heat-history API(1433行)；sectors_hot改用缓存(1434行)
- `static/index.html` — 删除commodity Tab+页面，新增heathistory Tab+loadHeatHistory函数

## Known Issues

- [ ] sector_heat.json只有当天数据，多天后才能看到连续排行

## Next Steps

1. [ ] 观察调度器热度记录是否正常积累
2. [ ] 累计多天后查看板块热度Tab的连续性

## Files to Review on Resume

- `server.py` — heat-history API + 调度器热度记录逻辑
- `static/index.html` — loadHeatHistory渲染函数
- `engine/decision.py` — 6维评分系统

---

## 已安装的股票Skills

**本机skills（直接可用）：**
- baostock, market-overview, stock-screener, realtime-monitor, smart-money-tracker, stock-analyst
- china-comps-analysis, china-dcf-model, china-initiating-coverage, china-macro-overview
- competitive-analysis, comps-analysis, idea-generation, pptx-author, sector-overview, tushare-data, xlsx-author
- chen-yiwei-perspective, tianchuan-perspective, chenyiwei-bbs

**插件skills（下次新会话生效）：**
- 63个: china-finance(31), investment-banking(10), private-equity(9), wealth-management(5), fund-admin(6), operations(2)

**克隆到本地的仓库：**
- baostock-skill, stock-sdk-mcp, china-financial-services, nigo-skills
