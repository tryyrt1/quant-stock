# 2026-06-05 交班 — ML评分 + 权重优化 + 原始指标

## 本次改动（三个阶段全部完成）

### 阶段一：权重动态调整 + 残差动量
- `engine/weight_optimizer.py` — 新建，每月根据历史胜率动态分配7维度权重
- `engine/indicators.py` — 新增 `calc_residual_momentum()` 60日去趋势残差动量
- `engine/decision.py` — `assess_volume()` 集成残差动量评分

### 阶段二：XGBoost ML评分
- `engine/ml_scorer.py` — 新建，XGBoost分类器
- 训练数据：660条历史预测，9维特征，准确率 85.8%
- `make_decision()` 中 ML评分×70% + 线性评分×30% 混合
- 每周自动重训练（周一15:01）

### 阶段三：原始指标特征（raw fields）
- `ml_scorer.py` 新增 `get_raw_fields()` 提取 RSI/量比/换手率/振幅/MA乖离率/5日涨跌幅
- `decision.py` ML评分调用传入 raw_fields
- 模型支持16维特征（9基础+7原始）

### 其他
- 底部系统状态栏（显示已部署功能列表）
- 每日一股改为每日两股（每次推荐2只）
- 周线评分+量价评分加入每日一股优中选优排名

### 涉及文件
- `engine/weight_optimizer.py` — 新建
- `engine/ml_scorer.py` — 新建
- `engine/indicators.py` — 新增残差动量
- `engine/decision.py` — ML集成+残差动量
- `server.py` — 调度器ML重训练+系统状态API
- `static/index.html` — 状态栏+双股展示
- `data/ml/model.pkl` — 训练好的模型

## 部署
- 云服务器已部署
- 需安装 xgboost（已装）
