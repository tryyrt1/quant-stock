"""技术指标计算 - Python版，用于后端生成报告"""
import math

def calc_ma(arr, days):
    r = []
    for i in range(len(arr)):
        if i < days - 1:
            r.append(None)
        else:
            r.append(sum(arr[i-days+1:i+1]) / days)
    return r

def calc_ema(arr, days):
    m = 2 / (days + 1)
    r, e = [], arr[0]
    for i in range(len(arr)):
        e = arr[0] if i == 0 else (arr[i] - e) * m + e
        r.append(e)
    return r

def calc_rsi(arr, days=14):
    r = []
    for i in range(len(arr)):
        if i < days:
            r.append(None)
            continue
        g = l = 0
        for j in range(i-days+1, i+1):
            d = arr[j] - arr[j-1]
            if d > 0: g += d
            else: l -= d
        r.append(50 if g+l == 0 else 100 - 100/(1+g/l))
    return r

def calc_macd(arr, fast=12, slow=26, sig=9):
    ef = calc_ema(arr, fast)
    es = calc_ema(arr, slow)
    dif = [ef[i]-es[i] for i in range(len(ef))]
    dea = calc_ema(dif, sig)
    macd = [2*(dif[i]-dea[i]) for i in range(len(dif))]
    return {'dif': dif, 'dea': dea, 'macd': macd}

def calc_kdj(kline, n=9):
    c = [k['close'] for k in kline]
    k_arr, d_arr = [], []
    pk = pd = 50
    for i in range(len(kline)):
        if i < n-1:
            k_arr.append(None); d_arr.append(None)
            continue
        hh = max(k['high'] for k in kline[i-n+1:i+1])
        ll = min(k['low'] for k in kline[i-n+1:i+1])
        rsv = (c[i]-ll)/(hh-ll)*100 if hh != ll else 50
        k = 2/3*pk + 1/3*rsv
        d = 2/3*pd + 1/3*k
        k_arr.append(k); d_arr.append(k)
        pk, pd = k, d
    return {'k': k_arr, 'd': d_arr, 'j': [3*k_arr[i]-2*d_arr[i] if k_arr[i] else None for i in range(len(k_arr))]}

def calc_boll(arr, days=20, mul=2):
    mid = calc_ma(arr, days)
    up, low = [], []
    for i in range(len(arr)):
        if mid[i] is None:
            up.append(None); low.append(None)
        else:
            s = sum((arr[j]-mid[i])**2 for j in range(i-days+1, i+1))
            std = math.sqrt(s/days)
            up.append(mid[i]+mul*std); low.append(mid[i]-mul*std)
    return {'mid': mid, 'upper': up, 'lower': low}

def check_golden_cross(arr, f=5, s=20):
    mf, ms = calc_ma(arr, f), calc_ma(arr, s)
    l = len(mf)
    return l>=2 and all(v is not None for v in [mf[l-2],ms[l-2],mf[l-1],ms[l-1]]) and mf[l-2]<=ms[l-2] and mf[l-1]>ms[l-1]

def check_oversold(arr, p=14, t=30):
    r = calc_rsi(arr, p)
    l = len(r)
    return l>=3 and all(v is not None for v in [r[l-3],r[l-2],r[l-1]]) and r[l-3]<t and r[l-2]<t and r[l-1]>t

def check_macd_gc(arr):
    d = calc_macd(arr)
    l = len(d['dif'])
    return l>=3 and d['dif'][l-2]<=d['dea'][l-2] and d['dif'][l-1]>d['dea'][l-1]

def calc_obv(klines):
    """计算OBV(能量潮)指标, 返回OBV值列表"""
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
            # 平盘不变
        obv.append(cum)
    return obv


def calc_biasvol(closes, volumes, period=20):
    """成交量加权乖离率 BIASVOL — A股最有效因子 (IC 0.0749)
    公式: BIAS = (close - MA) / MA, BIASVOL = BIAS * (volume / avg_volume)
    高成交量下的价格偏离比低成交量更有意义（趋势反转信号更强）
    """
    if len(closes) < period + 1:
        return []
    ma = calc_ma(closes, period)
    avg_vol = sum(volumes[-period:]) / period
    if avg_vol <= 0:
        return []
    result = []
    for i in range(len(closes)):
        if ma[i] is None or ma[i] == 0:
            result.append(None)
            continue
        bias = (closes[i] - ma[i]) / ma[i] * 100
        vol_ratio = volumes[i] / avg_vol
        result.append(round(bias * vol_ratio, 4))
    return result


def calc_vp_correlation(closes, volumes, period=20):
    """量价相关性系数 — A股最稳定因子 (IR 0.5975)
    滚动计算每日涨跌幅与成交量变化率的相关系数
    返回值: 最近period天的相关系数列表, 最后一个是当前值
    """
    if len(closes) < period + 2 or len(volumes) < period + 2:
        return []
    # 计算每日涨跌幅和成交量变化率
    returns = []
    vol_changes = []
    for i in range(1, len(closes)):
        if closes[i-1] > 0 and volumes[i-1] > 0:
            ret = (closes[i] - closes[i-1]) / closes[i-1] * 100
            vchg = (volumes[i] - volumes[i-1]) / volumes[i-1] * 100
            returns.append(ret)
            vol_changes.append(vchg)
    if len(returns) < period:
        return []
    result = []
    for i in range(period, len(returns) + 1):
        r_slice = returns[i-period:i]
        v_slice = vol_changes[i-period:i]
        n = len(r_slice)
        if n < 2:
            result.append(None)
            continue
        avg_r = sum(r_slice) / n
        avg_v = sum(v_slice) / n
        num = sum((r_slice[j] - avg_r) * (v_slice[j] - avg_v) for j in range(n))
        den_r = math.sqrt(sum((r_slice[j] - avg_r) ** 2 for j in range(n)))
        den_v = math.sqrt(sum((v_slice[j] - avg_v) ** 2 for j in range(n)))
        if den_r * den_v == 0:
            result.append(0)
        else:
            corr = num / (den_r * den_v)
            result.append(round(corr, 4))
    return result


def calc_support_resistance(kline):
    """
    计算压力位和支撑位
    使用三种方法综合：
    1. 枢轴点 (Pivot Points)
    2. 近期高/低点 (20日)
    3. 均线动态支撑/压力
    """
    closes = [k['close'] for k in kline]
    highs = [k['high'] for k in kline]
    lows = [k['low'] for k in kline]
    if len(kline) < 20:
        return {'R1': None, 'R2': None, 'S1': None, 'S2': None, 'near_term_high': None, 'near_term_low': None}

    # --- 1. 枢轴点 (取最近一根K线) ---
    last = kline[-1]
    h, l, c = last['high'], last['low'], last['close']
    pp = (h + l + c) / 3
    r1 = round(2 * pp - l, 2)
    r2 = round(pp + (h - l), 2)
    s1 = round(2 * pp - h, 2)
    s2 = round(pp - (h - l), 2)

    # --- 2. 近期高/低点 (20日) ---
    recent_high = max(highs[-20:])
    recent_low = min(lows[-20:])

    # --- 3. 均线动态支撑/压力 ---
    ma20 = calc_ma(closes, 20)
    ma60 = calc_ma(closes, 60)
    ma20_last = round(ma20[-1], 2) if ma20[-1] is not None else None
    ma60_last = round(ma60[-1], 2) if ma60[-1] is not None else None

    price = c
    # 判断当前价格相对于各支撑/压力的位置
    levels = {
        'R2': r2,
        'R1': r1,
        'Pivot': round(pp, 2),
        'S1': s1,
        'S2': s2,
        'recent_high': round(recent_high, 2),
        'recent_low': round(recent_low, 2),
        'ma20': ma20_last,
        'ma60': ma60_last,
    }

    # 找出最近的支撑和压力
    resistances = [v for k, v in levels.items() if v is not None and v > price]
    supports = [v for k, v in levels.items() if v is not None and v < price]

    nearest_resistance = min(resistances) if resistances else round(price * 1.05, 2)
    nearest_support = max(supports) if supports else round(price * 0.95, 2)

    # 计算到支撑/压力的距离(%)
    dist_to_resistance = round((nearest_resistance - price) / price * 100, 2)
    dist_to_support = round((price - nearest_support) / price * 100, 2)

    # 压力/支撑强度评估
    def strength(level, is_resistance):
        count = 0
        for i in range(len(highs) - 20, len(highs)):
            if is_resistance:
                if abs(highs[i] - level) / level < 0.01:
                    count += 1
            else:
                if abs(lows[i] - level) / level < 0.01:
                    count += 1
        if count >= 3: return '强'
        if count >= 1: return '中'
        return '弱'

    return {
        'R1': r1, 'R2': r2,
        'S1': s1, 'S2': s2,
        'recent_high': round(recent_high, 2),
        'recent_low': round(recent_low, 2),
        'ma20': ma20_last,
        'ma60': ma60_last,
        'nearest_resistance': nearest_resistance,
        'nearest_support': nearest_support,
        'dist_to_resistance': dist_to_resistance,
        'dist_to_support': dist_to_support,
        'resistance_strength': strength(nearest_resistance, True),
        'support_strength': strength(nearest_support, False),
    }
