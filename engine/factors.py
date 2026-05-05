"""多因子分析引擎 - 评分模型"""

def analyze_factors(kline_data, quote, news_sentiment=0, sr=None):
    """
    多因子评分 (0-100)
    因子维度: 价值、质量、动量、技术、情绪、支撑压力
    """
    closes = [k['close'] for k in kline_data]
    if len(closes) < 60:
        return {'error': '数据不足', 'score': 50, 'detail': {}}

    scores = {}

    # 1. 价值因子 (权重20%)
    pe = abs(quote.get('pe', 0) or 0)
    pb = abs(quote.get('pb', 0) or 0)
    value_score = 50
    if pe > 0:
        if pe < 15: value_score = 85
        elif pe < 25: value_score = 70
        elif pe < 40: value_score = 50
        elif pe < 80: value_score = 30
        else: value_score = 15
    if pb > 0 and pb < 1: value_score = min(90, value_score + 10)
    if pb > 10: value_score = max(10, value_score - 10)
    scores['value'] = {'score': value_score, 'weight': 0.20, 'desc': f'PE={pe:.1f}, PB={pb:.2f}'}

    # 2. 质量因子 (ROE替代, 权重15%)
    # 从股价走势简单推导质量（连续上涨通常隐含基本面改善）
    recent_60 = closes[-60:]
    ret_60 = (recent_60[-1] - recent_60[0]) / recent_60[0] if recent_60[0] != 0 else 0
    quality = 50 + ret_60 * 100
    quality = max(10, min(90, quality))
    scores['quality'] = {'score': quality, 'weight': 0.15, 'desc': f'60日涨幅={ret_60*100:.1f}%'}

    # 3. 动量因子 (权重25%)
    periods = [(5, 0.3), (20, 0.3), (60, 0.4)]
    momentum = 0
    momentum_detail = []
    for p, w in periods:
        if len(closes) > p:
            ret = (closes[-1] - closes[-p-1]) / closes[-p-1] * 100
        else:
            ret = 0
        s = 50 + ret * 2
        s = max(0, min(100, s))
        momentum += s * w
        momentum_detail.append(f'{p}日涨幅={ret:.1f}%')
    scores['momentum'] = {'score': round(momentum, 1), 'weight': 0.25, 'desc': ', '.join(momentum_detail)}

    # 4. 技术因子 (权重25%)
    tech = 50
    tech_detail = []

    # RSI
    from .indicators import calc_rsi
    rsi = calc_rsi(closes, 14)
    rsi_last = rsi[-1] if rsi[-1] is not None else 50
    if rsi_last < 30: tech += 15; tech_detail.append('RSI超卖')
    elif rsi_last > 70: tech -= 15; tech_detail.append('RSI超买')
    else: tech += 5; tech_detail.append('RSI中性')

    # MACD
    from .indicators import calc_macd, check_macd_gc
    if check_macd_gc(closes):
        tech += 15; tech_detail.append('MACD金叉')
    macd = calc_macd(closes)
    l = len(macd['macd'])
    if l > 1 and macd['macd'][l-1] > 0 and macd['macd'][l-2] < 0:
        tech += 5; tech_detail.append('MACD翻红')

    # 均线
    from .indicators import check_golden_cross
    if check_golden_cross(closes):
        tech += 10; tech_detail.append('均线金叉')

    tech = max(0, min(100, tech))
    scores['technical'] = {'score': tech, 'weight': 0.25, 'desc': ', '.join(tech_detail)}

    # 5. 情绪因子 (权重10%)
    sentiment = 50 + news_sentiment * 20
    sentiment = max(10, min(90, sentiment))
    scores['sentiment'] = {'score': round(sentiment, 1), 'weight': 0.10,
                          'desc': f'新闻情感分={news_sentiment:.2f}'}

    # 6. 支撑压力因子 (权重15%)
    sr_score = 50
    sr_detail = []
    price = quote.get('price', 0)
    if sr and price > 0:
        dist_up = sr.get('dist_to_resistance', 999)
        dist_dn = sr.get('dist_to_support', 999)
        nearest_r = sr.get('nearest_resistance', 0)
        nearest_s = sr.get('nearest_support', 0)

        # 价格接近支撑位 → 买入信号
        if dist_dn < 3:
            sr_score += 20
            sr_detail.append(f'接近支撑位({nearest_s})')
        # 价格接近压力位 → 卖出信号
        if dist_up < 3:
            sr_score -= 20
            sr_detail.append(f'接近压力位({nearest_r})')
        # 突破压力位 → 看涨
        if price > nearest_r and sr.get('resistance_strength') in ('中','强'):
            sr_score += 15
            sr_detail.append('突破压力位')
        # 跌破支撑位 → 看跌
        if price < nearest_s and sr.get('support_strength') in ('中','强'):
            sr_score -= 15
            sr_detail.append('跌破支撑位')
        # 布林带
        boll_upper = nearest_r * 1.02  # approximate
        boll_lower = nearest_s * 0.98
        if price <= boll_lower * 1.02:
            sr_score += 10
            sr_detail.append('触及布林下轨')
        if price >= boll_upper * 0.98:
            sr_score -= 10
            sr_detail.append('触及布林上轨')

        sr_score = max(5, min(95, sr_score))
    else:
        sr_detail.append('数据不足')
    scores['sr'] = {'score': sr_score, 'weight': 0.15, 'desc': ', '.join(sr_detail) if sr_detail else '中性'}

    # 综合评分
    total = sum(v['score'] * v['weight'] for v in scores.values())
    total = round(max(0, min(100, total)), 1)

    # 买入/卖出建议 (结合S/R)
    # 如果价格在支撑位附近，提升建议等级
    price = quote.get('price', 0)
    sr_boost = 0
    if sr and price > 0:
        dist_dn = sr.get('dist_to_support', 999)
        if dist_dn < 3: sr_boost = 5  # 接近支撑，加分
        dist_up = sr.get('dist_to_resistance', 999)
        if dist_up < 3: sr_boost = -5  # 接近压力，减分

    adjusted = max(0, min(100, total + sr_boost))

    if adjusted >= 68:
        advice = '买入'
        suggestions = []
        if sr and price > 0 and sr.get('dist_to_support', 999) < 3:
            suggestions.append(f'接近支撑位{sr["nearest_support"]}，可逢低建仓')
        if sr and sr.get('dist_to_resistance', 999) < 5:
            suggestions.append(f'上方压力位{sr["nearest_resistance"]}，注意止盈')
        reason = '多数因子表现积极' + ('，' + '；'.join(suggestions) if suggestions else '，建议建仓或加仓')
    elif adjusted >= 55:
        advice = '持有'
        reason = '各因子表现中性，建议持有观察'
        if sr and price > 0 and sr.get('dist_to_support', 999) < 3:
            reason += f'，接近支撑位{sr["nearest_support"]}可择机加仓'
        if sr and price > 0 and sr.get('dist_to_resistance', 999) < 3:
            reason += f'，接近压力位{sr["nearest_resistance"]}注意回调风险'
    elif adjusted >= 40:
        advice = '观望'
        reason = '部分因子偏弱，建议谨慎观望'
    else:
        advice = '卖出'
        reason = '多项因子表现不佳，建议减仓回避'

    return {
        'score': total,
        'adjusted_score': adjusted,
        'advice': advice,
        'reason': reason,
        'sr_boost': sr_boost,
        'detail': scores,
        'levels': {
            '价值': round(scores['value']['score']),
            '质量': round(scores['quality']['score']),
            '动量': round(scores['momentum']['score']),
            '技术': round(scores['technical']['score']),
            '情绪': round(scores['sentiment']['score']),
            '支撑压力': round(scores['sr']['score']),
        }
    }
