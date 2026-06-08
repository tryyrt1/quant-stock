# Session Handoff: 估值选股模式 + 估值分析模块

**Date:** 2026-06-08 **Project:** quant-stock-pro **Session Duration:** ~1.5h

## Current State

**Task:** 新增估值高与价格低背离选股模式 + 个股估值深度分析 **Phase:** 已部署到云服务器 **Progress:** 90%

## What We Did

1. **选股模式** — 新增 `估值高与价格低背离` 模式（检测价格低位+破均线+RSI偏低+PE>30），注册到ALL_PATTERNS，只显示标签不参与评分
2. **个股估值分析** — 新建 `engine/valuation.py`，通过 baostock 拉财报自算 PE/PB，新增 API `/api/stock/<code>/valuation`，前端增加估值分析按钮显示对比表

## Decisions Made

- **只显示标签不加分** — 估值模式仅作参考标记，不影响每日一股评分
- **自算 PB = epsTTM / roeAvg** — 通过会计恒等式 EPS/ROE = BVPS 推算每股净资产
- **估值分析不画图** — 只显示自算值 vs 市场值对比表 + 偏离度

## Code Changes

**Files modified:**

- `engine/patterns.py` — 新增 `pattern_valuation_price_divergence()`，注册到 ALL_PATTERNS
- `server.py` — 每日一股循环中注入估值标签；新增 `/api/stock/<code>/valuation` 接口
- `static/index.html` — patternOrder 横盘启动后插入、配色、估值按钮+函数

**Files created:**

- `engine/valuation.py` — 估值分析引擎（baostock 拉财报 → 自算 TTM PE/PB → 对比市场报价）

## 未完成 / 已知问题

- [ ] **BVPS 计算逻辑需修复** — `valuation.py` 中 `BVPS = epsTTM / roeAvg`，当前优先取到 Q1 数据时：epsTTM 是全年滚动、roeAvg 是单季 ROE，两者不匹配导致 BVPS 虚高、PB 虚低。需改为仅取年报Q4数据
- [ ] 板块 PE 中位数依赖 sectors.json 中的 pe_median 字段，目前缓存中可能没有该字段

## Next Steps

1. [ ] 修复 `valuation.py` 中 BVPS 计算：只取 Q4 年报数据的 epsTTM 和 roeAvg
2. [ ] 处理板块 PE 中位数缺失的问题

## Files to Review on Resume

- `engine/valuation.py` — 核心估值引擎，需要改 BVPS 计算逻辑
- `engine/patterns.py` — 估值高与价格低背离模式函数
- `server.py` — 估值 API 端点
