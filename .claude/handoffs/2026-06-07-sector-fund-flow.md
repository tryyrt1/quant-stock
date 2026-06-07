# Session Handoff: 板块追踪增加资金流入双榜排名

**Date:** 2026-06-07 **Project:** quant-stock-pro **Session Duration:** ~1h

## Current State

**Task:** 板块追踪页增加资金流入数据 + 双榜排名 **Phase:** 已部署 **Progress:** 100%

## What We Did

在板块追踪页新增了板块主力资金流入数据，支持双榜排名显示。

## 改动内容

### `engine/sectors.py`
- `fetch_hot_boards()` 末尾新增 **Step 3 — 全板块资金流聚合**
  - 遍历全部 CONCEPT_MAP（30+概念板块）的去重成分股（约200只）
  - 使用 `ThreadPoolExecutor(10)` 并发拉取东方财富主力净流入日线接口
  - 按板块汇总净流入，全板块排序
  - **资金流入榜 Top 10**（标注 `flow_rank`）
  - **热度榜 Top 10**（标注 `heat_rank`，跳过已在资金榜中的）
  - 同时标注热度榜板块在资金流入中的排位（`flow_rank`）
- 文件顶部新增 `import concurrent.futures`

### `static/index.html`
- `renderHotSectors()` 显示双榜标签：
  - `💰资金流入第N名` / `🔥热度第N名`（两榜共存时用 `·` 拼接）
  - 右上角显示 `💰+/-XXX万` 主力净流入额（绿色正/红色负）

## 数据源

- 个股资金流：东方财富 `push2.eastmoney.com/api/qt/stock/fflow/daykline/get`
- 当日实时数据（盘中动态更新，收盘后锁定）

## 已知问题

- 资金流入前10中未进入 Step 1 初筛前16的板块缺少 heat/形态数据，卡片显示不完整
- 全板块资金流聚合约耗时 10-15s，整次扫描约 40-60s

## Next Steps

无待办事项。

## Files to Review on Resume

- `engine/sectors.py:497-610` — Step 3 资金流聚合 + 双榜排序逻辑
- `static/index.html:1265-1292` — 双榜前端渲染
