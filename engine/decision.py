"""综合决策引擎 — 整合技术面/资金面/基本面/板块面, 输出明确买卖信号"""
from .indicators import calc_ma, calc_rsi, calc_macd, check_golden_cross, check_macd_gc


def assess_trend(closes):
    """趋势评分 (0-100), 权重30%"""
    if len(closes) < 60:
        return 50, ["数据不足"]

    price = closes[-1]
    ma20 = calc_ma(closes, 20)[-1] or price
    ma60 = calc_ma(closes, 60)[-1] or price

    pct_ma20 = (price - ma20) / ma20 * 100
    pct_ma60 = (price - ma60) / ma60 * 100

    score = 50
    reasons = []
    ma5_list = calc_ma(closes, 5)
    ma5 = ma5_list[-1] if ma5_list[-1] else price

    # MA5 vs MA20 金叉/死叉
    if len(ma5_list) >= 2 and ma5_list[-2] and ma5_list[-1]:
        ma20_list = calc_ma(closes, 20)
        if len(ma20_list) >= 2 and ma20_list[-2] and ma20_list[-1]:
            if ma5_list[-2] <= ma20_list[-2] and ma5_list[-1] > ma20_list[-1]:
                score += 15
                reasons.append("MA5上穿MA20(金叉)")
            elif ma5_list[-2] >= ma20_list[-2] and ma5_list[-1] < ma20_list[-1]:
                score -= 15
                reasons.append("MA5下穿MA20(死叉)")

    # 价格在MA20上方还是下方
    if pct_ma20 > 0:
        score += min(15, pct_ma20 * 2)
        reasons.append(f"站上MA20 (+{pct_ma20:.1f}%)")
    else:
        score -= min(15, abs(pct_ma20) * 2)
        reasons.append(f"跌破MA20 ({pct_ma20:.1f}%)")

    # 价格在MA60上方还是下方
    if pct_ma60 > 5:
        score += 10
        reasons.append(f"远在MA60上方 (+{pct_ma60:.1f}%)")
    elif pct_ma60 < -5:
        score -= 10
        reasons.append(f"远在MA60下方 ({pct_ma60:.1f}%)")
    elif pct_ma60 > 0:
        score += 5
        reasons.append(f"在MA60上方 (+{pct_ma60:.1f}%)")
    else:
        score -= 5
        reasons.append(f"在MA60下方 ({pct_ma60:.1f}%)")

    # 短期方向: 最近5天涨跌
    if len(closes) >= 10:
        ret_5 = (closes[-1] - closes[-6]) / closes[-6] * 100
        if ret_5 > 3:
            score += 8
            reasons.append(f"近5日上涨 {ret_5:.1f}%")
        elif ret_5 < -3:
            score -= 8
            reasons.append(f"近5日下跌 {ret_5:.1f}%")
        else:
            reasons.append(f"近5日横盘 {ret_5:.1f}%")

    return max(0, min(100, score)), reasons


def assess_patterns(patterns):
    """形态评分 (0-100), 权重25%"""
    if not patterns:
        return 30, ["无形态匹配"]

    score = 30
    reasons = []
    bullish_keys = {"golden_cross", "obv_breakout", "obv_consecutive",
                    "obv_bullish", "consecutive_up", "one_limitup",
                    "pre_breakout", "long_shadow", "low_vol_surge"}
    bearish_keys = {"oversold"}  # 超跌偏中性, 可能是机会也可能是风险

    for p in patterns:
        key = p.get("key", "")
        name = p.get("name", key)
        if key in bullish_keys:
            score += 10
            reasons.append(f"看多: {name}")
        elif key in bearish_keys:
            score -= 5
            reasons.append(f"风险: {name}")

    return max(0, min(100, score)), reasons


def assess_price_level(closes, sr):
    """价格位置评分 (0-100), 权重20%"""
    if not sr or len(closes) < 20:
        return 50, ["数据不足"]

    price = closes[-1]
    score = 50
    reasons = []

    # 距支撑位距离
    dist_support = sr.get("dist_to_support", 999)
    if dist_support < 2:
        score += 20
        reasons.append(f"临近支撑位(仅{dist_support:.1f}%)")
    elif dist_support < 5:
        score += 10
        reasons.append(f"接近支撑位({dist_support:.1f}%)")
    elif dist_support < 10:
        score += 5
        reasons.append(f"距支撑位{dist_support:.1f}%")

    # 距压力位距离
    dist_resistance = sr.get("dist_to_resistance", 999)
    if dist_resistance < 2:
        score -= 20
        reasons.append(f"临近压力位(仅{dist_resistance:.1f}%)")
    elif dist_resistance < 5:
        score -= 10
        reasons.append(f"接近压力位({dist_resistance:.1f}%)")

    # 突破压力位 → 看涨
    nearest_r = sr.get("nearest_resistance", 0)
    if price > nearest_r and nearest_r > 0:
        score += 15
        reasons.append("已突破压力位")
        # 突破后距离压力位多远
        pct_above_r = (price - nearest_r) / nearest_r * 100
        if pct_above_r > 10:
            score -= 10  # 离突破位太远, 追高风险
            reasons.append(f"但已高出压力位{pct_above_r:.1f}%")

    # 跌破支撑位 → 看跌
    nearest_s = sr.get("nearest_support", 0)
    if price < nearest_s and nearest_s > 0:
        score -= 15
        reasons.append("已跌破支撑位")

    # 近期区间位置
    recent_high = sr.get("recent_high", 0)
    recent_low = sr.get("recent_low", 0)
    if recent_high > recent_low and price > 0:
        pos_pct = (price - recent_low) / (recent_high - recent_low) * 100
        if pos_pct < 25:
            score += 10
            reasons.append(f"处于近期低位的{pos_pct:.0f}%分位")
        elif pos_pct > 75:
            score -= 10
            reasons.append(f"处于近期高位的{pos_pct:.0f}%分位, 追高谨慎")
        else:
            reasons.append(f"处于近期区间中部")

    return max(0, min(100, score)), reasons


def assess_volume(closes, klines):
    """量能评分 (0-100), 权重10%"""
    if len(klines) < 20:
        return 50, ["数据不足"]

    score = 50
    reasons = []
    vols = [k["volume"] for k in klines]
    closes_arr = [k["close"] for k in klines]

    # 均量
    vol_ma20 = sum(vols[-20:]) / 20
    last_vol = vols[-1]

    if vol_ma20 > 0:
        vol_ratio = last_vol / vol_ma20
        # 最近5天价格方向
        if len(closes) >= 6:
            ret_5 = (closes[-1] - closes[-6]) / closes[-6] * 100
            if vol_ratio > 1.5 and ret_5 > 0:
                score += 20
                reasons.append(f"放量上涨(量比{vol_ratio:.1f})")
            elif vol_ratio > 1.5 and ret_5 < 0:
                score -= 15
                reasons.append(f"放量下跌(量比{vol_ratio:.1f})")
            elif vol_ratio < 0.6 and ret_5 > 0:
                score -= 10
                reasons.append("缩量上涨(量比<0.6), 上涨乏力")
            elif vol_ratio < 0.6 and ret_5 < 0:
                score += 5
                reasons.append("缩量下跌(量比<0.6), 抛压减轻")
            else:
                reasons.append(f"量能正常(量比{vol_ratio:.1f})")

    # OBV趋势判断
    obv = calc_obv_from_klines(klines)
    if len(obv) >= 10:
        obv_5ago = obv[-6] if len(obv) > 6 else obv[0]
        obv_trend = (obv[-1] - obv_5ago) / abs(obv_5ago) * 100 if obv_5ago != 0 else 0
        if obv_trend > 3:
            score += 8
            reasons.append("OBV上升, 资金流入")
        elif obv_trend < -3:
            score -= 8
            reasons.append("OBV下降, 资金流出")

    return max(0, min(100, score)), reasons


def calc_obv_from_klines(klines):
    obv = []
    cum = 0
    for i in range(len(klines)):
        if i == 0:
            cum = klines[i]["volume"]
        else:
            if klines[i]["close"] > klines[i-1]["close"]:
                cum += klines[i]["volume"]
            elif klines[i]["close"] < klines[i-1]["close"]:
                cum -= klines[i]["volume"]
        obv.append(cum)
    return obv


def assess_sector(sector_ctx=None):
    """板块评分 (0-100), 权重15%"""
    if not sector_ctx:
        return 50, ["暂无板块数据"]

    score = 50
    reasons = []

    up = sector_ctx.get("up_count", 0)
    down = sector_ctx.get("down_count", 0)
    total = up + down
    if total > 0:
        up_ratio = up / total * 100
        if up_ratio >= 70:
            score += 20
            reasons.append(f"板块强势(上涨{up_ratio:.0f}%)")
        elif up_ratio >= 55:
            score += 10
            reasons.append(f"板块偏强(上涨{up_ratio:.0f}%)")
        elif up_ratio <= 30:
            score -= 20
            reasons.append(f"板块弱势(仅{up_ratio:.0f}%上涨)")
        elif up_ratio <= 45:
            score -= 10
            reasons.append(f"板块偏弱(仅{up_ratio:.0f}%上涨)")
        else:
            reasons.append(f"板块震荡(上涨{up_ratio:.0f}%)")

        # 板块内形态数量
        pat_count = sector_ctx.get("pattern_count", 0)
        if pat_count >= 5:
            score += 10
            reasons.append(f"板块内{pat_count}只股票有形态")
        elif pat_count >= 2:
            score += 5

    return max(0, min(100, score)), reasons


def make_decision(closes, klines, patterns, sr, sector_ctx=None):
    """综合决策 — 返回明确买卖信号"""
    trend_score, trend_reasons = assess_trend(closes)
    pat_score, pat_reasons = assess_patterns(patterns)
    level_score, level_reasons = assess_price_level(closes, sr)
    vol_score, vol_reasons = assess_volume(closes, klines)
    sector_score, sector_reasons = assess_sector(sector_ctx)

    weights = {
        "trend": 0.30,
        "patterns": 0.25,
        "price_level": 0.20,
        "volume": 0.10,
        "sector": 0.15,
    }

    total = (
        trend_score * weights["trend"]
        + pat_score * weights["patterns"]
        + level_score * weights["price_level"]
        + vol_score * weights["volume"]
        + sector_score * weights["sector"]
    )
    total = round(max(0, min(100, total)), 1)

    # 信号映射
    if total >= 75:
        signal = "买入"
        sub = "强烈建议买入"
        color = "#ff4757"
    elif total >= 60:
        signal = "增持"
        sub = "可逢低加仓"
        color = "#ff6b81"
    elif total >= 45:
        signal = "持有"
        sub = "继续持有观察"
        color = "#00d2ff"
    elif total >= 30:
        signal = "减仓"
        sub = "考虑逐步减仓"
        color = "#ffa502"
    else:
        signal = "卖出"
        sub = "建议离场回避"
        color = "#2ed573"

    # 汇总理由 (每个维度取前2条)
    all_reasons = []
    seen = set()
    for r in trend_reasons + pat_reasons + level_reasons + vol_reasons + sector_reasons:
        if r not in seen:
            seen.add(r)
            all_reasons.append(r)

    return {
        "signal": signal,
        "sub": sub,
        "score": total,
        "color": color,
        "details": {
            "trend": {"score": trend_score, "reasons": trend_reasons, "weight": weights["trend"]},
            "patterns": {"score": pat_score, "reasons": pat_reasons, "weight": weights["patterns"]},
            "price_level": {"score": level_score, "reasons": level_reasons, "weight": weights["price_level"]},
            "volume": {"score": vol_score, "reasons": vol_reasons, "weight": weights["volume"]},
            "sector": {"score": sector_score, "reasons": sector_reasons, "weight": weights["sector"]},
        },
        "reasons": all_reasons[:10],
    }
