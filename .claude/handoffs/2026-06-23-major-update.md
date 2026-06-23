# Session Handoff: 重大更新 — 量比扫描Tab + 周线选股4条件

**Date:** 2026-06-23 **Project:** quant-stock-pro **Session Duration:** ~3h

## Current State

完成三大改动：删除两个旧Tab、新增量比扫描Tab、修改周线选股逻辑。全部已部署到服务器并push到GitHub。

## What We Did

1. **删除板块追踪 + 预测统计 Tab** — 前后端全部代码清理
2. **新增量比换手率扫描 Tab** — 全市场三档筛选（启动/主升征兆/吸筹）
3. **周线选股 3条件→4条件** — 增加月线抬头条件
4. **修复量比计算bug** — f[37]是成交额非量比，改为从K线数据计算
5. **修复卡死问题** — K线请求加超时限制 + 候选上限300只

## Decisions Made

- **量比从K线计算** — 腾讯API没有直接的量比字段，只能从近5日均量算
- **52周价格位置判定低位** — 利用东方财富API已有字段(f23/f24)，不增加请求
- **月线MA5拐头判定抬头** — 最简单有效，直接对比本月/上月月MA5
- **堆量条件放松** — 近5周至少3周递增即可，允许1根绿柱
- **换成>=4.7%门槛** — 用户要求"约等于5的也纳入"
- **缓存保留** — GET读取缓存/POST触发扫描，切换Tab不丢失结果
- **8:50定时扫描** — 盘前自动扫一次，盘中手动刷新

## Code Changes

**Files modified:**
- `server.py` — 量比扫描API + 52周高低点 + 量比解析 + 调度器8:50
- `static/index.html` — 新增量比扫描Tab + 删除两个旧Tab
- `weekly_scanner.py` — 新增月线判断 + 修改量条件为堆量模式

**New backups (本地留存):**
- `server.py.v2bak` — 本次修改前备份
- `index.html.v2bak` — 本次修改前备份
- `weekly_scanner.py.bak` — 本次修改前备份

## Tag

今天的全部代码已打标签：**`v20260623`**
```bash
git checkout tags/v20260623   # 恢复到今天所有代码
```

## Open Questions

- [ ] 量比扫描三档阈值是否需要调整（目前启动15只/主升3只/吸筹0只）
- [ ] 周线选股232只是否需要进一步筛选或调参

## Context to Remember

- 腾讯行情API的f[37]是成交额(万元)，不是量比
- 量比 = 今日成交量 / 近5日平均日成交量（从K线取）
- 服务器密钥 `quant_stock_auto` 和 GitHub SSH key `id_ed25519` 均无有效期限制
- GitHub git token `ghp_...` 已过期，但git走的是SSH协议不受影响

## Next Steps

1. [ ] 观察量比扫描结果，必要时调阈值
2. [ ] 观察周线选股232只表现
3. [ ] 每周五收盘后跑 `python weekly_scanner.py --upload`

## Files to Review on Resume

- `server.py:1925` — 量比扫描API（GET缓存 + POST扫描）
- `server.py:1952` — 两轮筛选逻辑（先换手率再K线算量比）
- `weekly_scanner.py:117` — 月K线获取函数
- `weekly_scanner.py:183` — 量条件（堆量+连续放大）
- `weekly_scanner.py:290` — 月线抬头判断函数
- `static/index.html:2118` — 量比扫描前端JS
