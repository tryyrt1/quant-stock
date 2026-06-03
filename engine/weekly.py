"""周线分析 — 基于周K线的选股信号"""
import math

def _ma(arr, n):
    if len(arr) < n:
        return None
    return sum(arr[-n:]) / n

def check_ma20_trend(weekly_kline):
    """20周线上翘 + 股价在其上"""
    closes = [k['close'] for k in weekly_kline]
    if len(closes) < 22:
        return {'ma20_up': False, 'price_above_ma20': False, 'ma20': None, 'score': 0}
    ma20_now = _ma(closes, 20)
    ma20_prev = _ma(closes[:-1], 20) if len(closes) >= 21 else ma20_now
    if None in (ma20_now, ma20_prev):
        return {'ma20_up': False, 'price_above_ma20': False, 'ma20': ma20_now, 'score': 0}
    cur_price = closes[-1]
    up = ma20_now > ma20_prev * 1.002  # 20周线微微上翘即算
    above = cur_price > ma20_now
    score = (1 if up else 0) * 15 + (1 if above else 0) * 15
    return {'ma20_up': up, 'price_above_ma20': above, 'ma20': round(ma20_now, 2), 'score': min(30, score)}

def check_consecutive_up(weekly_kline, n=3):
    """周连阳: 连续 n 周收阳 (close > open 或 close > prev_close)"""
    closes = [k['close'] for k in weekly_kline]
    if len(closes) < n + 1:
        return {'consecutive_weeks': 0, 'consecutive_count': 0, 'score': 0}
    count = 0
    for i in range(1, min(n + 2, len(closes))):
        if closes[-i] > closes[-i - 1]:
            count += 1
        else:
            break
    score = min(20, count * 7)
    return {'consecutive_count': count, 'consecutive_weeks': n, 'score': score}

def check_volume_shrink_rise(weekly_kline):
    """缩量上涨: 最近1-2周价格涨但成交量缩"""
    if len(weekly_kline) < 4:
        return {'shrink_rise': False, 'score': 0}
    w2, w1 = weekly_kline[-3], weekly_kline[-2]
    lw = weekly_kline[-1]
    # 最近两周价涨量缩
    if lw['close'] > w1['close'] and lw['volume'] < w1['volume']:
        score = 15
        return {'shrink_rise': True, 'weeks': 1, 'score': score}
    if (lw['close'] > w1['close'] and w1['close'] > w2['close'] and
        lw['volume'] < w1['volume'] and w1['volume'] < w2['volume']):
        score = 20
        return {'shrink_rise': True, 'weeks': 2, 'score': score}
    return {'shrink_rise': False, 'score': 0}

def check_engulfing(weekly_kline):
    """周线阳包阴: 本周阳线实体覆盖上周阴线实体"""
    if len(weekly_kline) < 2:
        return {'engulfing': False, 'score': 0}
    prev = weekly_kline[-2]
    curr = weekly_kline[-1]
    prev_bear = prev['close'] < prev['open']  # 上周阴
    curr_bull = curr['close'] > curr['open']  # 本周阳
    if prev_bear and curr_bull:
        prev_body = prev['open'] - prev['close']
        curr_body = curr['close'] - curr['open']
        if curr_body > prev_body * 0.8:  # 阳线实体覆盖阴线实体80%以上
            return {'engulfing': True, 'prev_range': round(prev['high'] - prev['low'], 2),
                    'curr_range': round(curr['high'] - curr['low'], 2), 'score': 15}
    return {'engulfing': False, 'score': 0}

def check_consolidation(weekly_kline, min_weeks=8, max_amp=0.25):
    """周线长时间横盘"""
    if len(weekly_kline) < min_weeks:
        return {'consolidation': False, 'weeks': len(weekly_kline), 'amplitude': None, 'score': 0}
    chunk = weekly_kline[-min_weeks:]
    highs = [k['high'] for k in chunk]
    lows = [k['low'] for k in chunk]
    avg_price = sum([k['close'] for k in chunk]) / len(chunk)
    amplitude = (max(highs) - min(lows)) / avg_price if avg_price else 0
    is_consolidation = amplitude < max_amp
    score = 15 if is_consolidation else 0
    return {'consolidation': is_consolidation, 'weeks': min_weeks,
            'amplitude': round(amplitude * 100, 1), 'score': score}

def check_volume_harmony(weekly_kline, weeks=5):
    """量价相随温和: 量价相关系数在 0.3~0.7 之间"""
    if len(weekly_kline) < weeks:
        return {'harmony': False, 'correlation': None, 'score': 0}
    chunk = weekly_kline[-weeks:]
    closes = [k['close'] for k in chunk]
    volumes = [k['volume'] for k in chunk]
    n = len(closes)
    if n < 3 or max(volumes) == 0:
        return {'harmony': False, 'correlation': None, 'score': 0}
    avg_c = sum(closes) / n
    avg_v = sum(volumes) / n
    num, d1, d2 = 0, 0, 0
    for i in range(n):
        dc = closes[i] - avg_c
        dv = volumes[i] - avg_v
        num += dc * dv
        d1 += dc * dc
        d2 += dv * dv
    denom = math.sqrt(d1 * d2) if d1 * d2 > 0 else 1
    corr = num / denom
    harm = 0.3 <= corr <= 0.7
    score = 10 if harm else 0
    return {'harmony': harm, 'correlation': round(corr, 2), 'score': score}

def assess_weekly(weekly_kline):
    """综合周线评分: 0-100 + 各项信号"""
    if not weekly_kline or len(weekly_kline) < 4:
        return {'score': 0, 'signals': {}, 'summary': '数据不足'}
    r1 = check_ma20_trend(weekly_kline)
    r2 = check_consecutive_up(weekly_kline)
    r3 = check_volume_shrink_rise(weekly_kline)
    r4 = check_engulfing(weekly_kline)
    r5 = check_consolidation(weekly_kline)
    r6 = check_volume_harmony(weekly_kline)
    r7 = check_ma_converge_spread(weekly_kline)
    total = r1['score'] + r2['score'] + r3['score'] + r4['score'] + r5['score'] + r6['score'] + r7['score']
    total = min(100, max(0, total))
    # 汇总文本
    parts = []
    if r1['ma20_up'] and r1['price_above_ma20']:
        parts.append('20周线上翘✅')
    else:
        parts.append('20周线未上翘')
    if r2['consecutive_count'] >= 2:
        parts.append(f'连阳{r2["consecutive_count"]}周')
    if r3['shrink_rise']:
        parts.append('缩量上涨')
    if r4['engulfing']:
        parts.append('阳包阴')
    if r5['consolidation']:
        parts.append(f'横盘{r5["amplitude"]}%')
    if r6['harmony']:
        parts.append('量价温和')
    summary = ' · '.join(parts) if parts else '无明显周线信号'
    return {
        'score': total,
        'summary': summary,
        'signals': {
            'ma20_trend': r1,
            'consecutive_up': r2,
            'volume_shrink_rise': r3,
            'engulfing': r4,
            'consolidation': r5,
            'volume_harmony': r6,
            'ma_converge_spread': r7,
        },
    }


def check_ma_converge_spread(weekly_kline):
    """周线均线粘合向上发散: MA5/MA10/MA20 粘合后发散向上"""
    closes = [k['close'] for k in weekly_kline]
    if len(closes) < 15:
        return {'converge_spread': False, 'score': 0}
    ma5 = _ma(closes, 5)
    ma10 = _ma(closes, 10)
    ma20 = _ma(closes, 20)
    if None in (ma5, ma10, ma20):
        return {'converge_spread': False, 'score': 0}
    spread = max(ma5, ma10, ma20) / min(ma5, ma10, ma20) - 1 if min(ma5, ma10, ma20) > 0 else 99
    diverging = ma5 > ma10 > ma20
    if diverging and spread < 0.08:
        return {'converge_spread': True, 'ma5': round(ma5, 2), 'ma10': round(ma10, 2),
                'ma20': round(ma20, 2), 'spread': round(spread * 100, 1), 'score': 20}
    return {'converge_spread': False, 'score': 0}
