# Session Handoff: Tushare Pro 接入 + 基本面数据全流程 + 实时追踪（用 Tushare 数据）

**Date:** 2026-06-14 **Project:** quant-stock-pro **Session Duration:** ~8h

## Current State

**Task:** Tushare Pro 接入完成，基本面数据全量采集并上传，实时追踪功能重建 **Phase:** 完成 **Progress:** 100%

## What We Did

1. 注册 Tushare Pro（200元/年到2000分），接入 `fina_indicator` 和 `daily_basic` 接口
2. 批量采集全市场3030只股票（排除北交所/创业板/科创板/ST）的 ROE/负债率/毛利率/增长等财务数据，耗时29分钟（之前 baostock 要20小时）
3. 创建统一数据层 `engine/tushare_provider.py`：令牌桶限速 + 缓存 + 降级
4. 基本信息面打入评分系统：`engine/decision.py` 新增第7维度（权重15%），`engine/factors.py` 质量因子改用真实 ROE
5. 创建 `screener_fundamentals.py`：本地筛选200只候选股（ROE>5%+负债<50%+毛利率>20%+增长>10%，不足则逐步放宽）
6. 创建 `engine/intraday_monitor.py`：盘中实时监控引擎，每5分钟扫腾讯批量报价
7. 重建前端「实时追踪」Tab：候选池列表（含实时价格）+ 异动列表
8. 数据 + 代码已上传服务器并重启运行

## Decisions Made

- **Tushare Pro 2000分档** — 够用 `fina_indicator`（基本面）+ `daily_basic`（全市场PE/PB），200元/年
- **按报告期批量查不可用** — 2000分档不支持 `fina_indicator(period=...)`，改逐只查 + 令牌桶限速（200次/分钟）
- **只换基本面数据，不换行情** — K线/报价/板块/资金流保持腾讯/东方财富/akshare原来源
- **候选池固定200只** — 本地筛选 → 生成 candidates.json → SCP上传，不轻易变动
- **监控只依赖腾讯实时报价** — 不碰K线（旧方案失败原因），每5分钟200只批量1秒完成

## 数据流

```
本地: screener_fundamentals.py(ROE>5%等) → data/candidates.json (200只)
     ↓ SCP
服务器: data/candidates.json → intraday_monitor每5分钟扫码(腾讯报价)
     ↓ API
前端 ⚡实时追踪 Tab: 候选池(含实时价格) + 异动列表
```

## Code Changes

**新建文件：**

- `engine/tushare_provider.py` — Tushare 统一数据层（限速/缓存/降级）
- `screener_fundamentals.py` — 基本面筛选器（本地运行，产出 candidates.json）
- `engine/intraday_monitor.py` — 盘中监控引擎（5分钟轮询200只候选池）

**修改文件：**

- `server.py` — 增加 Tushare daily_basic 启动加载、intraday monitor 启动、监控 API 路由
- `engine/factors.py` — `analyze_factors()` 新增 `fundamentals` 参数，质量因子改用真实 ROE/负债率/现金流评分
- `engine/decision.py` — 新增 `assess_fundamentals()`（10项子评分），`make_decision()` 第7维度权重15%，修复 ML 评分 bug
- `engine/fundamentals_loader.py` — 负债率异常修正（从 asset_to_equity 推导）
- `engine/weight_optimizer.py` — 注册 fundamentals 维度
- `batch_fundamentals.py` — 新增 `--source tushare` 模式
- `static/index.html` — 方法标签/维度条/独立信号 增加基本面显示，新增实时追踪Tab（候选池+异动）

## Key Files

| 文件 | 说明 |
|---|---|
| `screener_fundamentals.py` | 本地筛选200只候选股，产出 `data/candidates.json` |
| `engine/intraday_monitor.py` | 盘中监控，每5分钟扫腾讯报价，检测异动 |
| `engine/tushare_provider.py` | Tushare 统一接口，令牌桶200次/分钟 |
| `engine/fundamentals_loader.py` | 服务器端基本面数据懒加载器 |
| `data/candidates.json` | 200只候选股（本地生成，SCP上传） |
| `data/fundamentals/fundamentals_complete.json` | 3030只全量基本面数据（本地） |

## Tushare Token

Token 已写入服务器 systemd 配置和本地环境变量。日常使用无需重新配置。

## Known Issues

- [ ] 候选池股票名字为UTF-8编码，从 all_stocks.json 补全（screener_fundamentals.py 已处理）
- [ ] 非交易时段候选池价格显示为0 → 已加懒加载修正（从腾讯API拿收盘价）
- [ ] 前端实时追踪Tab偶尔因文件编辑冲突丢失 → 最后版本已修复并上传

## Next Steps

1. [ ] 明天开盘观察实时追踪Tab是否正常显示异动
2. [ ] 观察基本面评分对决策的影响效果
3. [ ] 如需调整候选池条件，本地跑 `python screener_fundamentals.py --roe 5` 后 SCP 上传
4. [ ] 每季度财报季后重跑 `batch_fundamentals.py --source tushare` 更新基本面数据

## Files to Review on Resume

- `engine/tushare_provider.py` — Tushare 令牌桶限速 + 缓存策略
- `screener_fundamentals.py` — 候选池筛选逻辑（ROE/负债率/毛利率/增长条件+逐步放宽）
- `engine/intraday_monitor.py` — 腾讯批量报价解析 + 异动检测规则
- `engine/decision.py:643` — `make_decision()` 7维权重和 `assess_fundamentals()` 评分
- `data/candidates.json` — 当前候选池（200只）
