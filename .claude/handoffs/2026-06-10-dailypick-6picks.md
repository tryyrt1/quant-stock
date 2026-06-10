# Session Handoff: 每日一股扩展6股 + 放量异动筛选

**Date:** 2026-06-10 **Project:** quant-stock-pro **Session Duration:** ~1.5h

## Current State

**Task:** 每日一股从4股扩展到6股，新增"低位放量异动"(5-6股) **Phase:** 已部署 **Progress:** 100%

## What We Did

1. **第5-6股: 低位放量异动** — 在每日一股中新增2个推荐位，全市场筛选条件：60日区间底部35% + 昨天比前天放量≥2.5倍阳线 + 当日涨幅<9%
2. **修复量价标签bug** — `_kline`字段不存在于scored列表中导致"数据不足"的显示问题
3. **扩展推荐总数** — 从2股→4股→6股

## 当前推荐结构（6股）

| 位次 | 标签 | 选择逻辑 |
|------|------|---------|
| 0-1 | ⭐ 今日推荐/次选 | 高分排序(加分后) |
| 2 | 🔄 横盘发现 | cb_bonus≥8落选股 |
| 3 | 🚀 早期启动 | 低位30%+量比>1.2+刚启动 |
| 4-5 | 📊 放量异动 | 低位35%+2.5倍量阳线 |

## Decisions Made

- **放量异动不限板块** — 最初要求从资金流入前20板块中选，但资金流API不可用，后改为全市场筛选
- **量价标签预计算** — 评分循环中直接用真实k线算好label存入scored，避免后面取不到数据

## Code Changes

**Modified:**
- `server.py` — 评分循环加vol_day_ratio/is_green字段；第5-6股逻辑；量价标签预计算；移除板块限制
- `static/index.html` — pickCard 6股标签/颜色区分；scan_summary加放量异动统计

## Known Issues

- [ ] 东方财富个股资金流API从云服务器IP无法访问，capital维度用OBV推算替代

## Next Steps

1. [ ] 观察放量异动选出的股票质量，必要时调整条件（量比阈值、区间位置）

## Files to Review on Resume

- `server.py` — compute_daily_pick() 完整6股选择流程
- `engine/decision.py` — assess_capital_flow() OBV降级逻辑
