"""机器学习评分 — 基于历史数据训练XGBoost模型"""
import json, os, pickle, time
import numpy as np
from xgboost import XGBClassifier

MODEL_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'ml')
MODEL_FILE = os.path.join(MODEL_DIR, 'model.pkl')
FEATURE_FILE = os.path.join(MODEL_DIR, 'features.json')


def _prepare_training_data():
    """从 predictions.json 提取特征和标签"""
    pred_file = os.path.join(os.path.dirname(__file__), '..', 'data', 'predictions', 'predictions.json')
    if not os.path.exists(pred_file):
        return None, None
    with open(pred_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    X, y = [], []
    for r in data:
        if not r.get('verified') or r.get('correct') is None:
            continue
        methods = r.get('methods', {})
        if not methods:
            continue
        # 特征：7维度评分 + 综合score + 信号 + 原始指标
        features = []
        for dim in ['trend', 'patterns', 'price_level', 'volume', 'sector', 'intraday', 'capital']:
            m = methods.get(dim, {})
            features.append(m.get('score', 50))
        features.append(r.get('score', 50))
        sig_map = {'买入':5, '增持':4, '持有':3, '减仓':2, '卖出':1}
        features.append(sig_map.get(r.get('signal','持有'), 3))
        # 原始指标（从raw_fields读取）
        raw = r.get('raw_fields', {})
        if raw:
            features.extend([
                raw.get('rsi', 50),
                raw.get('vol_ratio', 1),
                raw.get('turnover', 3),
                raw.get('amplitude', 3),
                raw.get('ma5_dist', 0),
                raw.get('ma20_dist', 0),
                raw.get('chg_5d', 0),
            ])
        X.append(features)
        y.append(1 if r.get('correct') else 0)

    return np.array(X), np.array(y)


def train():
    """训练XGBoost模型并保存"""
    X, y = _prepare_training_data()
    if X is None or len(X) < 100:
        print('[ml_scorer] 数据不足，跳过训练')
        return False

    print(f'[ml_scorer] 训练数据: {len(X)} 条, {len(X[0])} 维特征')
    model = XGBClassifier(
        n_estimators=100, max_depth=4, learning_rate=0.1,
        subsample=0.8, colsample_bytree=0.8,
        random_state=42, use_label_encoder=False, eval_metric='logloss'
    )
    model.fit(X, y)
    os.makedirs(MODEL_DIR, exist_ok=True)
    with open(MODEL_FILE, 'wb') as f:
        pickle.dump(model, f)
    # 保存特征信息
    with open(FEATURE_FILE, 'w', encoding='utf-8') as f:
        json.dump({'trained_at': time.strftime('%Y-%m-%d %H:%M:%S'), 'samples': len(X)}, f)

    # 评估
    acc = model.score(X, y)
    print(f'[ml_scorer] 训练完成: 准确率 {acc:.1%}, 保存至 {MODEL_FILE}')
    return True


def score(features_dict, raw_fields=None):
    """对单个样本评分，返回 0-100
    features_dict: {trend_score, ..., total_score, signal}
    raw_fields: {rsi, vol_ratio, turnover, amplitude, ma5_dist, ma20_dist, chg_5d}
    """
    if not os.path.exists(MODEL_FILE):
        return None

    with open(MODEL_FILE, 'rb') as f:
        model = pickle.load(f)

    dims = ['trend', 'patterns', 'price_level', 'volume', 'sector', 'intraday', 'capital']
    features = [features_dict.get(d, 50) for d in dims]
    features.append(features_dict.get('total_score', 50))
    sig_map = {'买入':5, '增持':4, '持有':3, '减仓':2, '卖出':1}
    features.append(sig_map.get(features_dict.get('signal','持有'), 3))
    if raw_fields:
        features.extend([
            raw_fields.get('rsi', 50),
            raw_fields.get('vol_ratio', 1),
            raw_fields.get('turnover', 3),
            raw_fields.get('amplitude', 3),
            raw_fields.get('ma5_dist', 0),
            raw_fields.get('ma20_dist', 0),
            raw_fields.get('chg_5d', 0),
        ])

    prob = model.predict_proba(np.array([features]))[0]
    correct_prob = prob[1] if len(prob) > 1 else prob[0]
    return int(correct_prob * 100)


def is_ready():
    return os.path.exists(MODEL_FILE)

def get_raw_fields(kline, quote=None):
    """从K线数据和行情中提取原始指标"""
    fields = {}
    if not kline or len(kline) < 20:
        return fields
    closes = [k['close'] for k in kline]
    try:
        from engine.indicators import calc_rsi
        ra = calc_rsi(closes, 14)
        fields['rsi'] = round(ra[-1], 1) if ra[-1] is not None else 50
    except: fields['rsi'] = 50
    vols = [k['volume'] for k in kline]
    avg_v = sum(vols[-20:])/20 if len(vols)>=20 else 1
    fields['vol_ratio'] = round(vols[-1]/avg_v, 2) if avg_v>0 else 1
    if quote:
        fields['turnover'] = round(quote.get('turnover', 3), 2)
    else: fields['turnover'] = 3
    amps = [(k['high']-k['low'])/k['low']*100 for k in kline[-20:] if k['low']>0]
    fields['amplitude'] = round(sum(amps)/len(amps), 2) if amps else 3
    cur = closes[-1]
    if len(closes)>=5: fields['ma5_dist'] = round((cur - sum(closes[-5:])/5)/cur*100, 2)
    else: fields['ma5_dist'] = 0
    if len(closes)>=20: fields['ma20_dist'] = round((cur - sum(closes[-20:])/20)/cur*100, 2)
    else: fields['ma20_dist'] = 0
    if len(closes)>=5: fields['chg_5d'] = round((closes[-1]-closes[-5])/closes[-5]*100, 2)
    else: fields['chg_5d'] = 0
    return fields
