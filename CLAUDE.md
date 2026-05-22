# quant-stock-pro

A 股量化选股 Web 应用。Flask 后端 + 静态前端，部署在腾讯云。

## 启动

```bash
cd ~/Desktop/python\ test/quant-stock-pro && python server.py
```

端口 8080，浏览器打开 `http://localhost:8080`。

## 项目结构

- `server.py` — Flask 主服务（定时扫描 + API）
- `engine/` — 核心逻辑：技术指标、形态识别、扫描引擎、支撑压力、板块数据、UZI分析、综合决策、预测回测
- `data/snapshots/` — 扫描快照
- `data/predictions/predictions.json` — 预测记录
- `.claude/handoffs/` — 会话交班文档（已纳入 git 管理，自动推送到 GitHub）
- `.claude/skills/handoff/SKILL.md` — handoff 技能（也可用 `/handoff`）

## 核心功能

- 定时扫描：7个时间点（09:25, 09:45, 10:10, 11:00, 13:30, 14:30, 15:10）
- 形态识别：11种（金叉、OBV放量突破、OBV连续流入、OBV多头、连续上涨、涨停、突破前高、长下影、缩量反弹、超跌、低位放量）
- 综合决策：5维加权评分（趋势30%、形态25%、价格位置20%、量能10%、板块15%）→ 买入/增持/持有/减仓/卖出
- 预测回测：每天09:45/11:00/15:10 记录预测，15:10自动验证次日收盘

## 云服务器

- 部署: `scp` 文件后 `sudo systemctl restart quant-stock`
- 连接信息见本地 `.ssh/config` 或环境变量 `$CLOUD_HOST`

## 日常操作

- 新会话开始：直接说需求即可
- 会话结束：让我生成 handoff → commit + push 到 GitHub
- 需要之前会话的上下文：引用 `.claude/handoffs/` 中的文件
