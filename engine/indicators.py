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




def classify_vp_weekly(klines, baseline=5, recent=5, vol_threshold=1.3, low_threshold=0.7, price_threshold=2.5):
    """量价关系周同比分类（近5日 vs 前5日）"""
    if len(klines) < baseline + recent:
        return {'type': '正常', 'label': '数据不足', 'color': 'gray', 'score': 0, 'reason': '', 'ratio': 1, 'avg_return': 0}
    chunk = klines[-(baseline + recent):]
    prev_chunk = chunk[:recent]
    curr_chunk = chunk[recent:]
    avg_vol_prev = sum(k['volume'] for k in prev_chunk) / len(prev_chunk)
    avg_vol_curr = sum(k['volume'] for k in curr_chunk) / len(curr_chunk)
    ratio = avg_vol_curr / avg_vol_prev if avg_vol_prev > 0 else 1
    returns = []
    for i in range(1, len(curr_chunk)):
        pc = curr_chunk[i-1]['close']
        cc = curr_chunk[i]['close']
        if pc > 0: returns.append((cc-pc)/pc*100)
    avg_ret = sum(returns)/len(returns) if returns else 0
    increased = ratio > vol_threshold
    decreased = ratio < low_threshold
    price_up = avg_ret >= price_threshold
    price_flat = avg_ret < price_threshold
    base_reason = f'周比={ratio:.2f}(近5日/前5日) | 近5日涨幅={avg_ret:.1f}% | '

    if increased and price_flat:
        r = base_reason + f'量增周比{ratio:.2f}但涨幅仅{avg_ret:.1f}%<{price_threshold}%=横盘放量'
        return {'type':'量增价平','label':'短期放量滞涨','color':'orange','score':0,'reason':r,'ratio':ratio,'avg_return':avg_ret}
    if increased and price_up:
        r = base_reason + f'量增(>{vol_threshold}x)+价涨(>{price_threshold}%)=放量上涨'
        return {'type':'量增价升','label':'短期放量上涨','color':'green','score':15,'reason':r,'ratio':ratio,'avg_return':avg_ret}
    if decreased and price_up:
        r = base_reason + f'量减(<{low_threshold}x)+价涨(>{price_threshold}%)=缩量上涨'
        return {'type':'量减价升','label':'短期缩量上涨','color':'orange','score':5,'reason':r,'ratio':ratio,'avg_return':avg_ret}
    if decreased and price_flat:
        r = base_reason + f'量减(<{low_threshold}x)+价平(<{price_threshold}%)=缩量横盘'
        return {'type':'量减价平','label':'短期缩量横盘','color':'gray','score':0,'reason':r,'ratio':ratio,'avg_return':avg_ret}
    r = base_reason + '量价关系正常'
    return {'type':'正常','label':'量价正常','color':'gray','score':0,'reason':r,'ratio':ratio,'avg_return':avg_ret}

def classify_vp_relationship(klines, baseline=120, recent=20, vol_threshold=1.3, low_threshold=0.7):
    """量价关系四形态分类"""
    if len(klines) < baseline:
        return {'type': '正常', 'label': '数据不足', 'color': 'gray', 'score': 0}
    chunk = klines[-baseline:]
    recent_chunk = chunk[-recent:]
    avg_vol_baseline = sum(k['volume'] for k in chunk) / len(chunk)
    avg_vol_recent = sum(k['volume'] for k in recent_chunk) / len(recent_chunk)
    closes = [k['close'] for k in chunk]
    recent_returns = []
    for i in range(1, len(recent_chunk)):
        prev_c = recent_chunk[i - 1]['close']
        cur_c = recent_chunk[i]['close']
        if prev_c > 0:
            recent_returns.append((cur_c - prev_c) / prev_c * 100)
    avg_return = sum(recent_returns) / len(recent_returns) if recent_returns else 0
    all_high = max(k['high'] for k in chunk)
    all_low = min(k['low'] for k in chunk)
    cur_price = closes[-1]
    price_pos = (cur_price - all_low) / (all_high - all_low) * 100 if all_high > all_low else 50
    vol_ratio = avg_vol_recent / avg_vol_baseline if avg_vol_baseline > 0 else 1
    increased = vol_ratio > vol_threshold
    decreased = vol_ratio < low_threshold
    price_up = avg_return >= 3
    price_flat = avg_return < 3
    is_low = price_pos < 30
    is_high = price_pos > 70

    # 构建推理原因
    reason_parts = []
    reason_parts.append(f'量比={vol_ratio:.2f}({recent}日/{baseline}日)')
    if increased:
        reason_parts.append(f'>{vol_threshold}=量增')
    elif decreased:
        reason_parts.append(f'<{low_threshold}=量减')
    reason_parts.append(f'涨幅={avg_return:.1f}%')
    if price_up:
        reason_parts.append(f'>={price_threshold if "price_threshold" in dir() else 3}%=价涨')
    else:
        reason_parts.append(f'<{price_threshold if "price_threshold" in dir() else 3}%=价平')
    reason_parts.append(f'价格在{baseline}日区间{price_pos:.0f}%')
    if is_low:
        reason_parts.append('=低位')
    elif is_high:
        reason_parts.append('=高位')
    base_reason = ' | '.join(reason_parts) + ' -> '
    
    if increased and price_flat:
        if is_low:
            return {'type':'量增价平','label':'低位吸筹，反转：低转高，买入','color':'green','score':10,'reason':base_reason+'量增价平+低位=吸筹信号'}
        elif is_high:
            return {'type':'量增价平','label':'高位出货，反转：高转低','color':'red','score':-10,'reason':base_reason+'量增价平+高位=出货信号'}
        return {'type':'量增价平','label':'量增价平(中位)','color':'orange','score':0,'reason':base_reason+'量增价平+中位=方向不明'}
    if increased and price_up:
        if is_high:
            return {'type':'量增价升','label':'放量冲顶，警惕反转','color':'red','score':-5,'reason':base_reason+'量增价升+高位=冲顶信号'}
        if is_low:
            return {'type':'量增价升','label':'持续买入','color':'green','score':15,'reason':base_reason+'量增价升+低位=启动信号'}
        return {'type':'量增价升','label':'健康上涨，持续买入','color':'green','score':15,'reason':base_reason+'量增价升+中位=健康上涨'}
    if decreased and price_up:
        return {'type':'量减价升','label':'缩量上涨，主力控盘好','color':'orange','score':5,'reason':base_reason+'量减价升=主力控盘'}
    if decreased and price_flat:
        return {'type':'量减价平','label':'缩量横盘，等待方向','color':'orange','score':0,'reason':base_reason+'量减价平=观望'}
    return {'type':'正常','label':'量价关系正常','color':'gray','score':0,'reason':base_reason+'各项指标在正常范围内'}


def calc_residual_momentum(closes, period=60):
    """多期限残差动量：线性回归去趋势后的残差动量"""
    if len(closes) < period + 5:
        return {'residual': 0, 'momentum': 0, 'score': 0}
    import math
    x = list(range(period))
    y = closes[-period:]
    mx = sum(x) / period; my = sum(y) / period
    num = sum((x[i] - mx) * (y[i] - my) for i in range(period))
    den = sum((x[i] - mx) ** 2 for i in range(period))
    slope = num / den if den != 0 else 0
    intercept = my - slope * mx
    # 残差 = 实际值 - 趋势值
    residuals = [y[i] - (slope * x[i] + intercept) for i in range(period)]
    cur_residual = residuals[-1]
    prev_residual = residuals[-2]
    # 残差动量 = 残差在扩大还是缩小
    momentum = cur_residual - prev_residual
    score = 0
    if cur_residual > 0 and momentum > 0: score = 10  # 正残差且扩大 = 强势
    elif cur_residual > 0: score = 5                    # 正残差 = 偏强
    elif cur_residual < 0 and momentum < 0: score = -10 # 负残差且扩大 = 弱势
    elif cur_residual < 0: score = -5                    # 负残差 = 偏弱
    return {'residual': round(cur_residual, 4), 'momentum': round(momentum, 4), 'score': score}

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

def calc_main_force_control(klines, turnover_rate=None, capital_scores=None, news_sentiment=None, index_klines=None):
    items = []
    total_score = 0
    if not klines or len(klines) < 20:
        return {'score': 0, 'level': '数据不足', 'items': []}
    closes = [k['close'] for k in klines]

    # 1. 缩量上涨
    up_days = 0; shrink_up_days = 0
    for i in range(1, min(21, len(klines))):
        if klines[-i]['close'] > klines[-i-1]['close']:
            up_days += 1
            if klines[-i]['volume'] < klines[-i-1]['volume']:
                shrink_up_days += 1
    if up_days > 0 and shrink_up_days / up_days > 0.5:
        s = min(15, int(shrink_up_days / up_days * 15))
        total_score += s
        items.append({'name':'缩量上涨','ok':True,'score':s,'reason':f'涨日{up_days}天中{shrink_up_days}天缩量'})
    else:
        items.append({'name':'缩量上涨','ok':False,'score':0,'reason':'涨日放量或无明显缩量'})

    # 2. 换手率
    if turnover_rate is not None and turnover_rate > 0:
        if turnover_rate < 1: s=15; r=f'换手率{turnover_rate}% 极低'
        elif turnover_rate < 3: s=12; r=f'换手率{turnover_rate}% 偏低'
        elif turnover_rate < 5: s=8; r=f'换手率{turnover_rate}% 中等'
        elif turnover_rate < 10: s=4; r=f'换手率{turnover_rate}% 偏高'
        else: s=0; r=f'换手率{turnover_rate}% 过高'
        total_score += s; items.append({'name':'换手率','ok':s>=8,'score':s,'reason':r})
    else:
        items.append({'name':'换手率','ok':False,'score':0,'reason':'无数据'})

    # 3. 筹码集中度
    try:
        mn = min(k['low'] for k in klines[-60:])
        mx = max(k['high'] for k in klines[-60:])
        if mx - mn > 0:
            bs = (mx - mn) / 25
            vp = [0.0]*25
            for k in klines[-60:]:
                lo = max(0, int((k['low']-mn)/bs))
                hi = min(24, int((k['high']-mn)/bs))
                if hi >= lo:
                    vb = k['volume']/(hi-lo+1)
                    for i in range(lo,hi+1): vp[i] += vb
            tv = sum(vp)
            pv = max(vp)
            if tv > 0:
                pr = pv/tv*100
                if pr>20: s=15; r=f'POC占比{pr:.1f}% 高度集中'
                elif pr>12: s=10; r=f'POC占比{pr:.1f}% 较集中'
                elif pr>6: s=5; r=f'POC占比{pr:.1f}% 一般'
                else: s=0; r=f'POC占比{pr:.1f}% 分散'
                total_score += s; items.append({'name':'筹码集中','ok':pr>12,'score':s,'reason':r})
    except: items.append({'name':'筹码集中','ok':False,'score':0,'reason':'计算失败'})

    # 4. 涨放量跌缩量
    uv, dv = [], []
    for i in range(1, min(41, len(klines))):
        if klines[-i]['close'] > klines[-i-1]['close']: uv.append(klines[-i]['volume'])
        else: dv.append(klines[-i]['volume'])
    au = sum(uv)/len(uv) if uv else 0
    ad = sum(dv)/len(dv) if dv else 0
    if ad>0 and au/ad>1.5: s=10; r=f'涨均量{au/10000:.0f}万 >> 跌均量{ad/10000:.0f}万'
    elif ad>0 and au/ad>1: s=5; r=f'涨略大于跌({au/ad:.1f}x)'
    else: s=0; r='涨跌量比不明显'
    total_score += s; items.append({'name':'涨放量跌缩量','ok':s>=5,'score':s,'reason':r})

    # 5. 资金流入
    if capital_scores and len(capital_scores)>0:
        inf = sum(1 for sc in capital_scores if (sc or 0)>50)
        if inf>=5: s=15; r=f'近{len(capital_scores)}日中{inf}日主力流入'
        elif inf>=3: s=10; r=f'近{len(capital_scores)}日中{inf}日主力流入'
        elif inf>=1: s=5; r=f'近{len(capital_scores)}日中{inf}日主力流入'
        else: s=0; r='主力无明显流入'
        total_score += s; items.append({'name':'资金流入','ok':inf>=3,'score':s,'reason':r})
    else: items.append({'name':'资金流入','ok':False,'score':0,'reason':'无数据'})

    # 6. 振幅平稳
    amps = [(k['high']-k['low'])/k['low']*100 for k in klines[-20:] if k['low']>0]
    aa = sum(amps)/len(amps) if amps else 5
    if aa<2.5: s=10; r=f'日均振幅{aa:.1f}% 极平稳'
    elif aa<4: s=6; r=f'日均振幅{aa:.1f}% 较平稳'
    elif aa<6: s=3; r=f'日均振幅{aa:.1f}% 正常'
    else: s=0; r=f'日均振幅{aa:.1f}% 波动大'
    total_score += s; items.append({'name':'振幅平稳','ok':aa<4,'score':s,'reason':r})

    # 7. 独立大盘
    if index_klines and len(index_klines)>=20 and len(closes)>=20:
        try:
            ic = [k['close'] for k in index_klines[-20:]]
            sr = [(closes[-i]-closes[-i-1])/closes[-i-1] for i in range(1,20)]
            ir = [(ic[-i]-ic[-i-1])/ic[-i-1] for i in range(1,20)]
            n=len(sr); as_=sum(sr)/n; ai=sum(ir)/n
            num=d1=d2=0
            for i in range(n):
                ds=sr[i]-as_; di=ir[i]-ai
                num+=ds*di; d1+=ds*ds; d2+=di*di
            import math
            cor=num/(math.sqrt(d1*d2) if d1*d2>0 else 1)
            if abs(cor)<0.2: s=10; r=f'与大盘相关{cor:.2f} 极独立'
            elif abs(cor)<0.4: s=6; r=f'与大盘相关{cor:.2f} 较独立'
            elif abs(cor)<0.6: s=3; r=f'与大盘相关{cor:.2f} 一般'
            else: s=0; r=f'与大盘相关{cor:.2f} 跟盘'
            total_score+=s; items.append({'name':'独立大盘','ok':abs(cor)<0.4,'score':s,'reason':r})
        except: items.append({'name':'独立大盘','ok':False,'score':0,'reason':'计算失败'})
    else: items.append({'name':'独立大盘','ok':False,'score':0,'reason':'数据不足'})

    # 8. 利空大涨
    if news_sentiment is not None and len(closes)>=2:
        dc=(closes[-1]-closes[-2])/closes[-2]*100
        if news_sentiment<-0.3 and dc>2: s=10; r=f'新闻偏空({news_sentiment:.1f})但涨{dc:.1f}%'
        elif news_sentiment<-0.2 and dc>1: s=5; r=f'新闻略空({news_sentiment:.1f})涨{dc:.1f}%'
        else: s=0; r='无明显利空大涨'
        total_score+=s; items.append({'name':'利空大涨','ok':s>=5,'score':s,'reason':r})
    else: items.append({'name':'利空大涨','ok':False,'score':0,'reason':'无数据'})

    total_score = min(100, max(0, total_score))
    if total_score >= 75: level='高度控盘'
    elif total_score >= 55: level='中度控盘'
    elif total_score >= 35: level='轻度控盘'
    else: level='无控盘'
    return {'score': total_score, 'level': level, 'items': items}
