"""量选股模式识别 - 基于K线数据的形态扫描"""
from .indicators import calc_ma, calc_rsi, calc_macd, check_golden_cross, check_macd_gc

def _safe_close(klines):
    return [k['close'] for k in klines]

def _safe_vol(klines):
    return [k['volume'] for k in klines]

def pattern_consecutive_up(klines, days=2, min_pct=3.0):
    """连续上攻: 连续N天每天涨幅 >= min_pct%"""
    if len(klines) < days + 1:
        return False, {}
    for i in range(days):
        idx = -(days - i)
        prev_close = klines[idx - 1]['close']
        cur_close = klines[idx]['close']
        if prev_close <= 0:
            return False, {}
        pct = (cur_close - prev_close) / prev_close * 100
        if pct < min_pct:
            return False, {}
    total_pct = (klines[-1]['close'] - klines[-days-1]['close']) / klines[-days-1]['close'] * 100
    # 成交量逐日递增检查
    vols = [klines[-(days - i)]['volume'] for i in range(days)]
    vol_up = all(vols[i] >= vols[i-1] for i in range(1, len(vols)))
    return True, {
        'days': days,
        'min_pct': min_pct,
        'total_gain': round(total_pct, 2),
        'vol_increasing': vol_up,
        'label': f'连续{days}天涨{min_pct}%↑ (累计{total_pct:+.2f}%)'
    }

def pattern_golden_cross(klines, fast=5, slow=20):
    """均线金叉: MA5上穿MA20"""
    if len(klines) < slow + 2:
        return False, {}
    closes = _safe_close(klines)
    ok = check_golden_cross(closes, fast, slow)
    if not ok:
        return False, {}
    ma_f = calc_ma(closes, fast)[-1]
    ma_s = calc_ma(closes, slow)[-1]
    return True, {
        'fast_ma': fast, 'slow_ma': slow,
        f'MA{fast}': round(ma_f, 2) if ma_f else None,
        f'MA{slow}': round(ma_s, 2) if ma_s else None,
        'label': f'MA{fast}上穿MA{slow}金叉'
    }

def pattern_macd_gc(klines):
    """MACD金叉: DIF上穿DEA"""
    if len(klines) < 35:
        return False, {}
    closes = _safe_close(klines)
    ok = check_macd_gc(closes)
    if not ok:
        return False, {}
    macd = calc_macd(closes)
    return True, {
        'dif': round(macd['dif'][-1], 3),
        'dea': round(macd['dea'][-1], 3),
        'macd': round(macd['macd'][-1], 3),
        'label': 'MACD金叉'
    }

def pattern_volume_breakout(klines, lookback=20, vol_factor=1.5):
    """放量突破: 价格突破20日最高价 + 成交量放大"""
    if len(klines) < lookback + 1:
        return False, {}
    recent_highs = [k['high'] for k in klines[-lookback:-1]]
    recent_vols = [k['volume'] for k in klines[-lookback:-1]]
    if not recent_highs or not recent_vols:
        return False, {}
    max_high = max(recent_highs)
    avg_vol = sum(recent_vols) / len(recent_vols)
    cur = klines[-1]
    if cur['close'] > max_high and cur['volume'] >= avg_vol * vol_factor:
        return True, {
            'break_level': round(max_high, 2),
            'volume_ratio': round(cur['volume'] / avg_vol, 2),
            'close': round(cur['close'], 2),
            'label': f'放量突破{lookback}日高点{max_high:.2f} (量比{cur["volume"]/avg_vol:.1f}x)'
        }
    return False, {}

def pattern_bullish_alignment(klines, periods=(5, 20, 60)):
    """多头排列: MA5 > MA20 > MA60 (短中长均线依次向上)"""
    p = [v for v in periods if v < len(klines)]
    if len(p) < 2:
        return False, {}
    closes = _safe_close(klines)
    mas = {}
    for d in p:
        m = calc_ma(closes, d)
        mas[d] = m[-1] if m[-1] is not None else 0
    vals = [mas[d] for d in p]
    if all(v is None or v == 0 for v in vals):
        return False, {}
    ok = all(vals[i] > vals[i+1] for i in range(len(vals)-1))
    if not ok:
        return False, {}
    return True, {
        **{f'MA{d}': round(mas[d], 2) for d in p},
        'label': f'多头排列 MA{" < ".join(str(d) for d in p)}: {", ".join(f"{round(mas[d],2)}" for d in p)}'
    }

def pattern_oversold_bounce(klines, rsi_period=14, oversold=30):
    """超卖反弹: RSI低于阈值后回升 + 收阳线"""
    if len(klines) < rsi_period + 3:
        return False, {}
    closes = _safe_close(klines)
    rsi = calc_rsi(closes, rsi_period)
    # 检查最近3根: RSI从超卖区回升
    l = len(rsi)
    if any(v is None for v in [rsi[l-3], rsi[l-2], rsi[l-1]]):
        return False, {}
    if rsi[l-3] < oversold and rsi[l-1] > rsi[l-2]:
        # 最近一根收阳线
        cur = klines[-1]
        if cur['close'] > cur['open']:
            return True, {
                'rsi': round(rsi[-1], 1),
                'rsi_min': round(min(rsi[l-3], rsi[l-2]), 1),
                'lowest_rsi': round(min(v for v in rsi if v is not None), 1),
                'label': f'RSI超卖反弹 ({rsi[-1]:.1f}, 最低{rsi[l-3]:.1f})'
            }
    return False, {}

def pattern_three_white(klines, min_total=5.0):
    """三连阳: 连续3根阳线 + 累计涨幅>min_total%"""
    if len(klines) < 4:
        return False, {}
    for i in range(3):
        k = klines[-3+i]
        if k['close'] <= k['open']:
            return False, {}
    start = klines[-4]['close']
    end = klines[-1]['close']
    total = (end - start) / start * 100
    if total < min_total:
        return False, {}
    return True, {
        'total_gain': round(total, 2),
        'label': f'三连阳 (累计涨幅{total:.2f}%)'
    }

def pattern_squeeze_breakout(klines, lookback=10, threshold=0.03):
    """均线粘合突破: MA5/MA10/MA20接近粘合后向上发散"""
    if len(klines) < lookback + 20:
        return False, {}
    closes = _safe_close(klines)
    ma5 = calc_ma(closes, 5)
    ma10 = calc_ma(closes, 10)
    ma20 = calc_ma(closes, 20)
    # 检查: 最新值都不为None
    if any(v[-1] is None for v in [ma5, ma10, ma20]):
        return False, {}
    # 过去N天各均线的最大偏差比例
    spreads = []
    for i in range(-lookback, 0):
        vals = [v[i] for v in [ma5, ma10, ma20]]
        if any(v is None for v in vals):
            return False, {}
        avg = sum(vals) / 3
        spread = max(abs(v - avg) / avg for v in vals)
        spreads.append(spread)
    # 粘合: 最大偏差都在阈值内
    if all(s < threshold for s in spreads):
        # 最近向上: 最近3日涨幅>0
        if closes[-1] > closes[-4]:
            return True, {
                'avg_spread': round(sum(spreads[-1:]) / len(spreads[-1:]), 4),
                'ma5': round(ma5[-1], 2),
                'ma10': round(ma10[-1], 2),
                'ma20': round(ma20[-1], 2),
                'label': f'均线粘合发散 (MA5:{ma5[-1]:.2f} MA10:{ma10[-1]:.2f} MA20:{ma20[-1]:.2f})'
            }
    return False, {}

# 所有模式列表: (name, display_name, func)
ALL_PATTERNS = [
    ('consecutive_up', '连续上攻', pattern_consecutive_up),
    ('golden_cross', '均线金叉', pattern_golden_cross),
    ('macd_gc', 'MACD金叉', pattern_macd_gc),
    ('volume_breakout', '放量突破', pattern_volume_breakout),
    ('bullish_alignment', '多头排列', pattern_bullish_alignment),
    ('oversold_bounce', '超卖反弹', pattern_oversold_bounce),
    ('three_white', '三连阳', pattern_three_white),
    ('squeeze_breakout', '粘合突破', pattern_squeeze_breakout),
]

def scan_patterns(klines_all):
    """
    对所有模式扫描分析
    klines_all: dict {code: kline_data}
    返回: {code: matched_patterns}
    """
    results = {}
    for code, kline in klines_all.items():
        matches = []
        for key, name, func in ALL_PATTERNS:
            try:
                ok, info = func(kline)
                if ok:
                    matches.append({'key': key, 'name': name, 'info': info})
            except Exception:
                pass
        if matches:
            results[code] = matches
    return results
