"""多因子分析引擎 - 评分模型"""


def _score_quality_from_fundamentals(fundamentals):
    """基于真实基本面数据打分 (0-100)，返回 (score, desc)。"""
    from engine.fundamentals_loader import get_loader
    fl = get_loader()

    # ── ROE (权重35%) ──
    roe = fl.get_roe(fundamentals)
    if roe is None:
        roe_score = 40
        roe_desc = "ROE=无数据"
    elif roe > 0.30:
        roe_score = 95
        roe_desc = f"ROE={roe*100:.1f}%"
    elif roe > 0.20:
        roe_score = 80
        roe_desc = f"ROE={roe*100:.1f}%"
    elif roe > 0.15:
        roe_score = 70
        roe_desc = f"ROE={roe*100:.1f}%"
    elif roe > 0.10:
        roe_score = 55
        roe_desc = f"ROE={roe*100:.1f}%"
    elif roe > 0.05:
        roe_score = 35
        roe_desc = f"ROE={roe*100:.1f}%"
    elif roe > 0:
        roe_score = 20
        roe_desc = f"ROE={roe*100:.1f}%"
    else:
        roe_score = 5
        roe_desc = f"ROE={roe*100:.1f}%(亏损)"

    # ── 毛利率 & 净利率 (权重15%) ──
    gp = fl.get_gp_margin(fundamentals)
    np = fl.get_np_margin(fundamentals)
    margin_score = 50
    margin_parts = []
    if gp is not None:
        margin_parts.append(f"毛利率={gp*100:.1f}%")
        if gp > 0.60:
            margin_score += 25
        elif gp > 0.40:
            margin_score += 15
        elif gp > 0.20:
            margin_score += 5
        elif gp < 0:
            margin_score -= 15
    if np is not None:
        margin_parts.append(f"净利率={np*100:.1f}%")
        if np > 0.20:
            margin_score += 15
        elif np > 0.10:
            margin_score += 8
        elif np > 0.05:
            margin_score += 3
        elif np < 0:
            margin_score -= 10
    margin_score = max(5, min(95, margin_score))

    # ── 负债率 & 速动比率 (权重20%) ──
    liab = fl.get_liab_ratio(fundamentals)
    quick = fl.get_quick_ratio(fundamentals)
    debt_score = 50
    debt_parts = []
    if liab is not None:
        debt_parts.append(f"负债率={liab*100:.0f}%")
        if liab < 0.30:
            debt_score += 25
        elif liab < 0.45:
            debt_score += 15
        elif liab < 0.60:
            debt_score += 5
        elif liab < 0.75:
            debt_score -= 5
        else:
            debt_score -= 15
    if quick is not None:
        debt_parts.append(f"速动比率={quick:.2f}")
        if quick > 1.5:
            debt_score += 10
        elif quick > 1.0:
            debt_score += 5
        elif quick < 0.5:
            debt_score -= 10
    debt_score = max(5, min(95, debt_score))

    # ── 现金流质量 (权重15%) ──
    cfo_to_np = fundamentals.get('years', {}).get(
        max(fundamentals.get('years', {})), {}).get('cfo_to_np')
    cfo_to_or = fundamentals.get('years', {}).get(
        max(fundamentals.get('years', {})), {}).get('cfo_to_or')
    cf_score = 50
    cf_parts = []
    if cfo_to_np is not None:
        cf_parts.append(f"现金流/净利={cfo_to_np:.2f}")
        if cfo_to_np > 1.2:
            cf_score += 25
        elif cfo_to_np > 0.8:
            cf_score += 15
        elif cfo_to_np > 0.5:
            cf_score += 5
        elif cfo_to_np > 0:
            cf_score -= 5
        else:
            cf_score -= 20
    if cfo_to_or is not None:
        cf_parts.append(f"现金/营收={cfo_to_or:.2f}")
    cf_score = max(5, min(95, cf_score))

    # ── 增长 (营收+利润, 权重15%) ──
    profit_g = fl.get_profit_growth(fundamentals)
    revenue_g = fl.get_revenue_growth(fundamentals)
    growth_score = 50
    growth_parts = []
    if profit_g is not None:
        growth_parts.append(f"净利润增={profit_g*100:.1f}%")
        if profit_g > 0.30:
            growth_score += 20
        elif profit_g > 0.15:
            growth_score += 12
        elif profit_g > 0:
            growth_score += 3
        elif profit_g > -0.15:
            growth_score -= 8
        else:
            growth_score -= 15
    if revenue_g is not None:
        growth_parts.append(f"营收增={revenue_g*100:.1f}%")
        if revenue_g > 0.20:
            growth_score += 10
        elif revenue_g > 0.10:
            growth_score += 5
        elif revenue_g > 0:
            growth_score += 2
        elif revenue_g < -0.10:
            growth_score -= 10
    growth_score = max(5, min(95, growth_score))

    # ── 综合 ──
    total = (roe_score * 0.35 + margin_score * 0.15 + debt_score * 0.20
             + cf_score * 0.15 + growth_score * 0.15)
    total = round(max(5, min(95, total)), 1)

    desc_parts = [roe_desc] + margin_parts + debt_parts + cf_parts + growth_parts
    desc = ', '.join(filter(None, desc_parts))
    return total, desc


def analyze_factors(kline_data, quote, news_sentiment=0, sr=None, fundamentals=None):
    """
    多因子评分 (0-100)
    因子维度: 价值、质量、动量、技术、情绪、支撑压力

    fundamentals: 来自 fundamentals_loader.get(code) 的字典或 None
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

    # 2. 质量因子 (权重15%)
    if fundamentals:
        quality, quality_desc = _score_quality_from_fundamentals(fundamentals)
    else:
        # 无基本面数据时回退到价格走势推导
        recent_60 = closes[-60:]
        ret_60 = (recent_60[-1] - recent_60[0]) / recent_60[0] if recent_60[0] != 0 else 0
        quality = 50 + ret_60 * 100
        quality = max(10, min(90, quality))
        quality_desc = f'60日涨幅={ret_60*100:.1f}%(无基本面)'
    scores['quality'] = {'score': quality, 'weight': 0.15, 'desc': quality_desc}

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
