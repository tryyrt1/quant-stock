# 2026-06-03 交班 — 量价关系四形态 + 自选股排序

## 本次改动

### 1. 量价关系四形态（engine/indicators.py + patterns.py + decision.py）
- 新增 `classify_vp_relationship()` 函数，120日基线 + 20日对比
- 四形态：量增价平、量增价升、量减价升、量减价平
- 根据价格位置（低位/中位/高位）给出不同操作提示
- 利好绿色、警告红色、中性橙色
- `assess_volume()` 增加量价形态加分

### 2. 选股模式形态列表
- 新增4个量价形态（vp_increase_flat/up, vp_decrease_up/flat）
- 排序在周线之后、连续上攻之前

### 3. 个股详情页 — 技术评分
- 显示后端分类结论（如"高位出货，反转：高转低"）
- 颜色标记：红/绿/橙

### 4. 自选股排序
- 新增自选股改为 `insert(0)` 放首位

### 5. 涉及文件
- `engine/indicators.py` — 新增 classify_vp_relationship
- `engine/patterns.py` — 新增4个VP形态
- `engine/decision.py` — assess_volume 加 VP 加分
- `server.py` — stock_detail 返回 vp 字段
- `static/index.html` — patternOrder + 技术评分展示

## 已知问题
- 量价形态需要全市场扫描或个股打开时才会触发判断
- 部分股票可能显示"量价关系正常"（确实没有极端量价表现）

## 部署
- 云服务器已部署
