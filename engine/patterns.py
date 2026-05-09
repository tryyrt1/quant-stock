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

def pattern_oversold(klines, lookback=60):
    """超跌筛选: 价格深跌远离均线 + RSI超卖 + 短期持续下跌"""
    if len(klines) < lookback + 10:
        return False, {}
    closes = _safe_close(klines)
    cur_close = klines[-1]['close']

    # 1. 价格低于 MA60 至少 15%
    ma60 = calc_ma(closes, 60)
    if ma60[-1] is None or ma60[-1] <= 0:
        return False, {}
    pct_below_ma60 = (cur_close - ma60[-1]) / ma60[-1] * 100
    if pct_below_ma60 > -15:
        return False, {}

    # 2. RSI(14) < 30 (超卖)
    rsi = calc_rsi(closes, 14)
    if rsi[-1] is None or rsi[-1] >= 30:
        return False, {}

    # 3. 20 日跌幅 > 10%
    if len(closes) >= 20:
        decline_20 = (closes[-1] - closes[-20]) / closes[-20] * 100
        if decline_20 > -8:
            return False, {}
    else:
        return False, {}

    return True, {
        'pct_below_ma60': round(pct_below_ma60, 2),
        'rsi': round(rsi[-1], 1),
        'decline_20d': round(decline_20, 2),
        'label': f'超跌: 低于MA60 {pct_below_ma60:.1f}%, RSI {rsi[-1]:.1f}, 20日跌{decline_20:.1f}%'
    }

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

# ===================== OBV 选股模式 =====================

def _calc_obv(klines):
    """内部OBV计算"""
    obv = []
    cum = 0
    for i in range(len(klines)):
        if i == 0:
            cum = klines[i]['volume']
        else:
            if klines[i]['close'] > klines[i-1]['close']:
                cum += klines[i]['volume']
            elif klines[i]['close'] < klines[i-1]['close']:
                cum -= klines[i]['volume']
        obv.append(cum)
    return obv


def pattern_obv_breakout(klines):
    """OBV价升创新高: OBV线在30日均线上方 + 股价上升 + OBV创新高"""
    if len(klines) < 60:
        return False, {}
    obv = _calc_obv(klines)
    obv_ma30 = calc_ma(obv, 30)

    # 最新OBV和MA30
    cur_obv = obv[-1]
    cur_ma30 = obv_ma30[-1]
    if cur_ma30 is None or cur_obv <= cur_ma30:
        return False, {}

    # OBV创新高: 最近60日最高
    if cur_obv <= max(obv[-60:-1]):
        return False, {}

    # 股价上升: 收盘价在5日均线上方 (短期趋势向上)
    closes = _safe_close(klines)
    ma5 = calc_ma(closes, 5)
    if ma5[-1] is None or klines[-1]['close'] < ma5[-1]:
        return False, {}

    # 最近3日涨幅为正
    recent_gain = (closes[-1] - closes[-4]) / closes[-4] * 100

    obv_range = max(obv[-60:]) - min(obv[-60:])
    obv_diff = cur_obv - cur_ma30
    obv_pct = (obv_diff / obv_range * 100) if obv_range != 0 else 0
    return True, {
        'obv_ma30': round(cur_ma30, 0),
        'obv_diff': round(obv_diff, 0),
        'obv_pct': round(obv_pct, 1),
        'recent_gain': round(recent_gain, 2),
        'label': f'OBV价升创新高 (OBV站上MA30, 近3日涨幅{recent_gain:+.2f}%)'
    }


def pattern_obv_flat(klines, lookback=60, max_net_ratio=0.3):
    """OBV横盘: OBV线在三个月及以上相对走平"""
    if len(klines) < lookback + 10:
        return False, {}
    obv = _calc_obv(klines)
    recent = obv[-lookback:]
    closes = _safe_close(klines)

    obv_start = recent[0]
    obv_end = recent[-1]
    obv_min = min(recent)
    obv_max = max(recent)
    obv_range = obv_max - obv_min

    if obv_range == 0:
        return False, {}

    # OBV横盘: 净变化占区间范围的比例小 (终点相对起点没有明显趋势)
    obv_net = obv_end - obv_start
    net_ratio = abs(obv_net) / obv_range

    if net_ratio > max_net_ratio:
        return False, {}

    price_change = (closes[-1] - closes[-lookback]) / closes[-lookback] * 100

    return True, {
        'period': lookback,
        'net_ratio': round(net_ratio, 2),
        'price_change_pct': round(price_change, 2),
        'obv_range': int(obv_range),
        'label': f'OBV横盘 ({lookback}天, 净变{obv_net:+.0f}, 区间{obv_range:.0f}, 价变{price_change:+.2f}%)'
    }


def pattern_obv_divergence(klines, lookback=60):
    """OBV底背离: 股价下跌但OBV横向移动(背离, 主力吸筹)"""
    if len(klines) < lookback + 10:
        return False, {}
    obv = _calc_obv(klines)
    closes = _safe_close(klines)

    recent_obv = obv[-lookback:]

    # 股价下跌 >= 3%
    price_change = (closes[-1] - closes[-lookback]) / closes[-lookback] * 100
    if price_change > -3:
        return False, {}

    # OBV变动: 用区间范围归一化, 避免OBV起始值接近0时百分比爆炸
    obv_start = recent_obv[0]
    obv_end = recent_obv[-1]
    obv_min = min(recent_obv)
    obv_max = max(recent_obv)
    obv_range = obv_max - obv_min

    if obv_range == 0:
        return False, {}

    # OBV净变化占区间范围的比例 (-1 ~ 1)
    obv_net = obv_end - obv_start
    obv_net_ratio = obv_net / obv_range

    # OBV没有明显下跌: 净变化比例 > -0.3 (最多下跌区间范围的30%)
    if obv_net_ratio < -0.3:
        return False, {}

    return True, {
        'price_change_pct': round(price_change, 2),
        'obv_net_ratio': round(obv_net_ratio, 2),
        'obv_net': int(obv_net),
        'obv_range': int(obv_range),
        'label': f'OBV底背离 (股价{price_change:+.2f}%, OBV区间净变{obv_net_ratio:+.0%}, 净{obv_net:+.0f})'
    }


def pattern_obv_plus_breakout(klines):
    """OBV+连涨: OBV价升创新高 + 连续上攻 双线共振"""
    ok1, info1 = pattern_obv_breakout(klines)
    if not ok1:
        return False, {}
    ok2, info2 = pattern_consecutive_up(klines)
    if not ok2:
        return False, {}
    return True, {
        'obv_info': info1.get('label', ''),
        'consecutive_days': info2.get('days', 0),
        'total_gain': info2.get('total_gain', 0),
        'label': f'OBV+连涨共振 (连涨{info2.get("days",0)}天{info2.get("total_gain",0):+.2f}%)'
    }


def pattern_long_lower_shadow(klines):
    """前天红K长下影线 + 昨日中阳线 (止跌反转组合)"""
    if len(klines) < 5:
        return False, {}

    # 前天 (index -3, -2是昨天, -1是今天)
    dby = klines[-3]
    yst = klines[-2]

    # ---- 前天: 红K长下影线 ----
    if dby['close'] <= dby['open']:
        return False, {}
    dby_body = dby['close'] - dby['open']
    dby_lower = dby['open'] - dby['low']
    dby_range = dby['high'] - dby['low']
    if dby_range <= 0:
        return False, {}
    # 下影线 >= 2倍实体 且 下影线占全波范围40%以上
    if dby_lower < 2 * dby_body or dby_lower < dby_range * 0.4:
        return False, {}

    # ---- 昨日: 中阳线 ----
    if yst['close'] <= yst['open']:
        return False, {}
    yst_body = yst['close'] - yst['open']
    yst_range = yst['high'] - yst['low']
    if yst_range <= 0:
        return False, {}
    yst_gain = (yst['close'] - yst['open']) / yst['open'] * 100
    yst_body_ratio = yst_body / yst_range
    # 涨幅1.5%~6%, 实体占范围20%~80%
    if yst_gain < 1.5 or yst_gain > 6:
        return False, {}
    if yst_body_ratio < 0.2 or yst_body_ratio > 0.8:
        return False, {}

    return True, {
        'dby_lower': round(dby_lower / dby_range * 100, 1),
        'yst_gain': round(yst_gain, 2),
        'yst_body_ratio': round(yst_body_ratio, 2),
        'label': f'前天长下影+昨中阳 (昨涨{yst_gain:.2f}%, 下影占前天{dby_lower/dby_range*100:.0f}%)'
    }


def pattern_one_limitup(klines):
    """首板涨停: 最近2个交易日内有且仅有一个涨停板"""
    if len(klines) < 3:
        return False, {}

    # 检查最近2根K线中恰好有1根是涨停
    count = 0
    limit_dates = []
    for i in range(2):
        idx = -(2 - i)          # idx = -2 昨天, idx = -1 今天
        prev = klines[idx - 1]
        cur = klines[idx]
        if prev['close'] > 0 and (cur['close'] - prev['close']) / prev['close'] >= 0.095:
            count += 1
            limit_dates.append((idx, cur['date'], (cur['close'] - prev['close']) / prev['close'] * 100))

    if count != 1:
        return False, {}

    idx, dt, pct = limit_dates[0]
    day_label = '今日' if idx == -1 else '昨日'

    return True, {
        'limit_day': 'today' if idx == -1 else 'yesterday',
        'date': dt,
        'limit_pct': round(pct, 2),
        'label': f'首板: {day_label}涨停 ({dt}, {pct:.2f}%)'
    }


# 所有模式列表: (name, display_name, func)
ALL_PATTERNS = [
    ('consecutive_up', '连续上攻', pattern_consecutive_up),
    ('golden_cross', '均线金叉', pattern_golden_cross),
    ('obv_breakout', 'OBV价升创新高', pattern_obv_breakout),
    ('obv_flat', 'OBV横盘', pattern_obv_flat),
    ('obv_divergence', 'OBV底背离', pattern_obv_divergence),
    ('obv_plus_breakout', 'OBV+连涨共振', pattern_obv_plus_breakout),
    ('long_lower_shadow', '长下影+中阳', pattern_long_lower_shadow),
    ('oversold', '超跌筛选', pattern_oversold),
    ('one_limitup', '首板涨停', pattern_one_limitup),
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
