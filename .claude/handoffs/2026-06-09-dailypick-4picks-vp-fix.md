# Session Handoff: 每日一股扩展4股 + 量价数据不足修复

**Date:** 2026-06-09 **Project:** quant-stock-pro **Session Duration:** ~2h

## Current State

**Task:** 每日一股从2股扩展到4股 + 修复量价标签"数据不足"bug **Phase:** 已部署 **Progress:** 100%

## What We Did

1. **每日一股4股** — 原先只推荐前2名高分股，现扩展为4股：前2名高分(现有)、第3名横盘发现(落选中cb_bonus≥8)、第4名早期启动(低位刚放量)
2. **量价标签bug** — 构建推荐卡片时`_kline`字段不存在于scored列表，传空数组给`classify_vp_relationship`导致显示"数据不足"
3. **数据源失败处理** — 资金流API不可用时降级用OBV+量价推算；板块/资金维度无数据从50分改为0分，前端显示"暂无数据"

## Decisions Made

- **第4股筛选条件** — 60日区间底部30% + 量比>1.2 + 3日累计涨2-15% + 当日涨幅<8% + 评分≥55
- **资金维度降级策略** — 东方财富API不通时用OBV+量价比推算（不如真数据准，但比0分好）

## Code Changes

**Modified:**
- `server.py` — 评分循环增加range_pos/vol_ratio/cum_3d_chg/早期启动第4股逻辑/量价标签预计算 (2700行区域)
- `static/index.html` — pickCard第3/4位标签+底色区分 (1190行区域)
- `engine/decision.py` — 板块/资金无数据返回0分；资金API失败时OBV降级 (224行, 433行)
- `engine/sectors.py` — 关键except加日志；资金流API超时5s→3s (408行, 527行)

## 未完成 / 已知问题

- [ ] 东方财富个股资金流API从云服务器IP无法访问，目前用OBV推算替代，精度不如真实数据

## Next Steps

1. [ ] 可以考虑其他资金流数据源替代东方财富（如新浪、腾讯level2）

## Files to Review on Resume

- `server.py` — compute_daily_pick() 整个函数，4股选择逻辑
- `engine/decision.py` — assess_capital_flow() + assess_sector() 的0分返回和OBV降级
- `static/index.html` — pickCard() 4股标签显示
