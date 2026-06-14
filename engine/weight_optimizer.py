"""权重动态优化 — 基于历史表现调整各维度权重"""
import json, os, time

WEIGHT_FILE = os.path.join(os.path.dirname(__file__), '..', 'data', 'dynamic_weights.json')

# 基础权重（8维度）
BASE_WEIGHTS = {
    'trend': 0.20,
    'patterns': 0.14,
    'price_level': 0.12,
    'volume': 0.07,
    'sector': 0.09,
    'intraday': 0.08,
    'capital': 0.15,
    'fundamentals': 0.15,
}

DIM_NAMES = {
    'trend': '趋势', 'patterns': '形态', 'price_level': '价位',
    'volume': '量能', 'sector': '板块', 'intraday': '分时',
    'capital': '资金', 'fundamentals': '基本面',
}


def _load_weights():
    if os.path.exists(WEIGHT_FILE):
        try:
            with open(WEIGHT_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return None


def _save_weights(data):
    os.makedirs(os.path.dirname(WEIGHT_FILE), exist_ok=True)
    with open(WEIGHT_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_weights():
    """返回当前权重。若本月已优化则用优化权重，否则返回基础权重"""
    cached = _load_weights()
    if cached:
        current_month = time.strftime('%Y-%m')
        if cached.get('month') == current_month:
            return cached.get('weights', BASE_WEIGHTS)
    return BASE_WEIGHTS


def calc_weights_from_predictions():
    """从 nextday.json 读取已验证预测，计算各维度上月胜率，重新分配权重"""
    pred_file = os.path.join(os.path.dirname(__file__), '..', 'data', 'predictions', 'nextday.json')
    if not os.path.exists(pred_file):
        return BASE_WEIGHTS

    try:
        with open(pred_file, 'r', encoding='utf-8') as f:
            records = json.load(f)
    except:
        return BASE_WEIGHTS

    # 只取已验证的、含methods的记录
    verified = [r for r in records if r.get('verified') and r.get('correct') is not None and r.get('methods')]
    if len(verified) < 10:
        return BASE_WEIGHTS

    # 统计每个维度在不同偏移上的胜率，取+1天偏移
    dim_perf = {}
    for dim in BASE_WEIGHTS:
        dim_perf[dim] = {'correct': 0, 'total': 0}

    for r in verified:
        correct = r.get('correct', False)
        methods = r.get('methods', {})
        for dim in BASE_WEIGHTS:
            m = methods.get(dim, {})
            if m.get('verified') and m.get('correct') is not None:
                dim_perf[dim]['total'] += 1
                if m['correct']:
                    dim_perf[dim]['correct'] += 1

    # 计算各维度胜率
    accuracies = {}
    for dim in BASE_WEIGHTS:
        t = dim_perf[dim]['total']
        c = dim_perf[dim]['correct']
        accuracies[dim] = (c / t * 100) if t > 0 else 50

    # 根据胜率分配权重（胜率越高权重越大）
    total_acc = sum(accuracies.values()) or 1
    new_weights = {}
    for dim in BASE_WEIGHTS:
        new_weights[dim] = round(accuracies[dim] / total_acc, 4)

    # 归一化确保总和=1
    total = sum(new_weights.values())
    if total > 0:
        new_weights = {k: round(v / total, 4) for k, v in new_weights.items()}

    # 保存
    result = {
        'month': time.strftime('%Y-%m'),
        'weights': new_weights,
        'accuracies': accuracies,
        'samples': {dim: dim_perf[dim]['total'] for dim in BASE_WEIGHTS},
        'updated_at': time.strftime('%Y-%m-%d %H:%M:%S'),
    }
    _save_weights(result)
    return new_weights


def get_weight_summary():
    """返回权重说明文本"""
    cached = _load_weights()
    if not cached:
        return '使用固定权重（无历史数据）'
    parts = []
    for dim, w in cached.get('weights', {}).items():
        name = DIM_NAMES.get(dim, dim)
        acc = cached.get('accuracies', {}).get(dim, 0)
        samples = cached.get('samples', {}).get(dim, 0)
        parts.append(f'{name}:{w*100:.0f}%(胜率{acc:.0f}%)')
    return ' | '.join(parts)
