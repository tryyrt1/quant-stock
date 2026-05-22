# Session Handoff: quant-stock-pro 完整项目状态

**日期:** 2026-05-21 **项目:** quant-stock-pro **会话时长:** 多轮长会话

## 当前状态

**任务:** A 股量化选股 Web 应用（自选股扫描 + 板块扫描 + 技术分析 + 综合决策 + 预测回测）  
**阶段:** 功能完整，已部署到云服务器  
**进度:** 核心功能已完成，正在使用中

## 项目结构

```
quant-stock-pro/
├── server.py                    # Flask 主服务 (端口 8080)
├── requirements.txt
├── engine/
│   ├── __init__.py
│   ├── indicators.py            # 技术指标 (MA/RSI/MACD/金叉)
│   ├── patterns.py              # 11 种形态识别
│   ├── scanner.py               # 扫描引擎 (扫雷/基本面/UZI)
│   ├── support_resistance.py    # 支撑位/压力位
│   ├── sector.py                # 板块数据
│   ├── uzi.py                   # UZI 分析 (抄底逃顶)
│   ├── decision.py              # 综合决策引擎 (5 维评分)
│   └── prediction_tracker.py    # 预测追踪与回测
├── data/
│   ├── snapshots/               # 定时扫描结果快照
│   └── predictions/
│       └── predictions.json     # 预测记录 + 验证结果
├── static/
│   └── index.html               # 前端页面
└── .claude/
    ├── skills/handoff/SKILL.md  # handoff 技能 (本地)
    └── handoffs/                # 交班文档目录
```

## 核心功能

### 定时扫描 (scheduler)
- 7 个时间点: 09:25, 09:45, 10:10, 11:00, 13:30, 14:30, 15:10
- 每 30 秒检查一次当前时间是否到扫描时间
- 扫描自选股 + 所有板块成分股
- 记录快照到 `data/snapshots/`

### 板块配置 (sector.py)
- 预定义板块映射（CONCEPT_MAP），不依赖外部 API
- 覆盖板块: 钠电池, 半导体, 电子, 光模块, CPU, 锂电池, 光伏, 人工智能, 机器人, 低空经济, 创新药, 券商, 军工, 消费电子, 汽车零部件, 储能, 风电

### 形态识别 (patterns.py) — 11 种
- 金叉, OBV放量突破, OBV连续流入, OBV多头, 连续上涨, 涨停, 突破前高, 长下影, 缩量反弹, 超跌, **低位放量**

### 综合决策 (decision.py) — 5 维加权评分
- 趋势 30% + 形态 25% + 价格位置 20% + 量能 10% + 板块 15%
- 信号: ≥75 买入, ≥60 增持, ≥45 持有, ≥30 减仓, <30 卖出

### 预测回测 (prediction_tracker.py)
- 每天 3 个时间点记录: 09:45, 11:00, 15:10
- 同一股票 + 同日 + 同时段去重
- 15:10 扫描完成后自动验证（取次日收盘价对比）
- 按信号类型统计准确率

### API 端点
- `GET /api/scan` — 手动触发扫描
- `GET /api/scan/status` — 扫描状态
- `GET /api/stock/<code>/snapshots` — 股票快照
- `GET /api/stock/<code>/decision` — 综合决策（含5维评分明细）
- `GET /api/stock/<code>/uzi` — UZI 分析
- `GET /api/stocks/watchlist` — 自选股列表
- `GET /api/stocks/sector/<sector>` — 板块成分股
- `GET /api/sectors` — 所有板块
- `GET /api/predictions/stats?code=X` — 预测统计
- `POST /api/predictions/verify` — 触发验证
- `GET /api/predictions/recent?days=7` — 近期验证结果

### 前端页面 (index.html)
- 4 个 tab: 选股模式, 板块选股, 个股详情, 预测统计
- 个股详情包含: 基础行情, 形态信号, 综合决策面板, UZI 分析

## 云服务器

- **服务路径:** `/home/ubuntu/quant-stock/`
- **服务名:** `quant-stock` (systemd)
- **部署命令:** 见本地 `deploy_cloud.bat` 或 `$CLOUD_HOST` 环境变量

## 做出的关键决策

- **板块数据不依赖外部 API** — East Money push2 在云服务器被墙，改用预定义 CONCEPT_MAP
- **预测回测独立验证** — 验证不依赖扫描范围，逐只独立取 K 线判断
- **3 个时间点** — 不是 7 个时间点都记录预测，只在 09:45/11:00/15:10 记录
- **去重策略** — 同一股票 + 同日 + 同时段覆盖更新，不产生重复记录
- **"持有"信号不计入总体准确率** — 仅展示在按信号类型细分统计中

## 待办/可改进点

- [ ] 预测统计 tab 的数据可能为空（刚部署还没产生预测记录），需要等定时扫描运行后才有数据
- [ ] handoff 技能已安装到 `~/.claude/skills/handoff/`（全局）和项目本地，新会话可用 `/handoff`

## 关键代码位置

- `server.py:280-340` — 定时扫描逻辑 (scheduler)
- `server.py:518-576` — 决策 API (make_decision 调用)
- `server.py:580-620` — 预测统计 API
- `engine/decision.py:262-330` — 综合决策主函数
- `engine/prediction_tracker.py:35-66` — 预测记录
- `engine/prediction_tracker.py:69-143` — 验证逻辑
- `engine/scanner.py` — 扫描引擎
- `engine/patterns.py` — 形态识别 (含 低位放量)

## 用户偏好

- 中文界面，A 股市场
- 偏好直接执行不反复确认（"拿到目标后一口气做完"）
- 项目在 `C:\Users\Administrator\Desktop\python test\quant-stock-pro\`
- GitHub: tryyrt1
- 云服务器: 腾讯云 (IP 见本地环境变量)

## 下一会话继续的入口

1. 新会话中打开项目目录，输入 `/handoff` 可生成新的交班文档
2. 或直接阅读本文件恢复上下文
3. 检查 `data/predictions/predictions.json` 看是否有预测记录生成
4. 检查 `data/snapshots/` 看定时扫描是否正常运行
5. 如需重新部署到云服务器，参考上面的部署命令
