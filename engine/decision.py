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
                    "pre_breakout", "long_shadow", "low_vol_surge",
                    "biasvol_buy", "vp_confirm"}
    bearish_keys = {"oversold", "vp_divergence"}  # vp_divergence=量价背离,风险信号

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
        return 0, ["暂无板块数据"]

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


def assess_intraday(quote, closes, klines=None, hour=None, minute=None):
    """分时评分 (0-100), 权重10%
    quote: 实时行情 {price, open, high, low, volume, yesterdayClose}
    closes: 日K线收盘价列表（用于判断趋势方向）
    klines: 完整日K线（用于获取均量数据），可选
    hour, minute: 当前时间（用于时间加权指标），可选，默认用time.localtime()
    """
    import time as _time
    if not quote or not quote.get('price'):
        return 50, ["暂无分时数据"]

    price = quote['price']
    yesterday_close = quote.get('yesterdayClose', 0)
    today_open = quote.get('open', 0)
    today_high = quote.get('high', 0)
    today_low = quote.get('low', 0)

    if yesterday_close <= 0:
        return 50, ["分时数据不足"]

    # 计算开盘以来经过的交易时间（小时）
    if hour is None or minute is None:
        now = _time.localtime()
        hour, minute = now.tm_hour, now.tm_min
    # 上午09:30~11:30=2h, 下午13:00~15:00=2h, 共4小时
    if hour < 12:
        elapsed = max(0, (hour - 9) + (minute - 30) / 60) if hour >= 9 else 0
    else:
        elapsed = 2 + max(0, (hour - 13) + minute / 60)  # 下午最多2小时
    elapsed = min(elapsed, 4)  # 不超过4小时

    score = 50
    reasons = []

    gap_pct = (today_open - yesterday_close) / yesterday_close * 100 if yesterday_close else 0
    now_pct = (price - yesterday_close) / yesterday_close * 100
    gap_diff = now_pct - gap_pct  # 正=开盘后走强, 负=开盘后走弱

    # ── 1. 开盘走势 + 盘中方向 (0-25分) ──
    if gap_pct > 1.5:
        reasons.append(f"高开{gap_pct:.1f}%")
        if gap_diff > -1:
            score += 16; reasons.append("开盘强势")
        elif gap_diff < -2:
            score -= 12; reasons.append("高开低走,抛压大")
        else:
            score += 5
    elif gap_pct < -1.5:
        reasons.append(f"低开{gap_pct:.1f}%")
        if gap_diff > 1:
            score += 16; reasons.append("低开高走,承接强")
        elif gap_diff < -1:
            score -= 10; reasons.append("低开低走,弱势")
        else:
            score -= 5
    else:
        reasons.append(f"平开({gap_pct:+.1f}%)")
        if gap_diff > 2:
            score += 10; reasons.append("盘中走强")
        elif gap_diff < -2:
            score -= 10; reasons.append("盘中走弱")

    # ── 2. 日内动量 + 位置 (0-25分) ──
    # 2a. 从开盘到现在的涨跌幅（衡量日内方向强度）
    intraday_chg = (price - today_open) / today_open * 100 if today_open else 0
    if elapsed > 0.5:  # 至少交易30分钟才有意义
        # 每小时涨跌幅（消除时间差异）
        hourly_rate = intraday_chg / elapsed
        if hourly_rate > 1.5:
            score += 12; reasons.append(f"日内强势(时涨{hourly_rate:.1f}%)")
        elif hourly_rate > 0.5:
            score += 8; reasons.append(f"日内偏强(时涨{hourly_rate:.1f}%)")
        elif hourly_rate < -1.5:
            score -= 10; reasons.append(f"日内弱势(时跌{hourly_rate:.1f}%)")
        elif hourly_rate < -0.5:
            score -= 5; reasons.append(f"日内偏弱(时跌{hourly_rate:.1f}%)")
        else:
            reasons.append(f"日内震荡(时变{hourly_rate:+.1f}%)")
    else:
        # 开盘不久，直接用开盘走势
        pass

    # 2b. 日内相对位置（叠加）
    if today_high > today_low and price > 0:
        pos_pct = (price - today_low) / (today_high - today_low) * 100
        trend_up = len(closes) >= 10 and (closes[-1] - closes[-10]) / closes[-10] * 100 > 3 if closes else False
        if pos_pct < 15:
            if trend_up:
                score += 13; reasons.append("回调至低位(上升趋势)")
            else:
                score += 5; reasons.append("日内低位")
        elif pos_pct > 85:
            if trend_up:
                score += 5; reasons.append("主动追高(上升趋势)")
            else:
                score -= 10; reasons.append("高位追涨(弱势)")
        else:
            reasons.append(f"日内中部")

    # ── 3. 当前涨跌幅 + 加速度 (0-15分) ──
    # 3a. 当前涨幅
    if abs(now_pct) < 1:
        score += 5; reasons.append(f"涨跌幅适中({now_pct:+.1f}%)")
    elif now_pct > 3 and now_pct <= 5:
        score += 8; reasons.append(f"上涨{now_pct:+.1f}%")
    elif now_pct > 5:
        score += 3; reasons.append(f"涨幅已大{now_pct:+.1f}%")
    elif now_pct >= -3 and now_pct < 0:
        score -= 3; reasons.append(f"微跌{now_pct:+.1f}%")
    elif now_pct < -3 and now_pct >= -5:
        score -= 8; reasons.append(f"下跌{now_pct:+.1f}%")
    elif now_pct < -5:
        score -= 5; reasons.append(f"大跌{now_pct:+.1f}%")

    # 3b. 开盘后走势加速度（盘中方向一致性）
    if elapsed > 1 and abs(intraday_chg) > 0.5:
        consistency = abs(gap_diff) > abs(intraday_chg) * 0.3 if abs(intraday_chg) > 0 else True
        if gap_diff > 1 and consistency:
            score += 5; reasons.append("持续走强")
        elif gap_diff < -1 and consistency:
            score -= 5; reasons.append("持续走弱")

    # ── 4. 量比 + 时间加权量 (0-20分) ──
    vol = quote.get('volume', 0)
    # 从klines计算均量（修正之前的bug）
    avg_vol = 0
    if klines and len(klines) >= 20:
        avg_vol = sum(k['volume'] for k in klines[-20:]) / 20
    elif len(closes) >= 20:
        # fallback: 如果没有klines，跳过精确的量比
        pass

    if avg_vol > 0 and elapsed > 0:
        # 时间加权预期成交量 = 日均量 * 已过时间/4小时
        expected_vol = avg_vol * (elapsed / 4)
        vol_ratio = vol / expected_vol if expected_vol > 0 else 0

        if vol_ratio > 1.5 and now_pct > 1:
            score += 12; reasons.append(f"放量上攻(量比{vol_ratio:.1f})")
        elif vol_ratio > 1.5 and now_pct < -1:
            score -= 12; reasons.append(f"放量下杀(量比{vol_ratio:.1f})")
        elif vol_ratio < 0.4 and now_pct > 0:
            score -= 8; reasons.append("缩量上涨,动能不足")
        elif vol_ratio < 0.4 and now_pct < -0.5:
            score += 5; reasons.append("缩量下跌,抛压减轻")
        elif vol_ratio < 0.3:
            score -= 3; reasons.append("量能极度萎缩")

        # 量价背离检测
        if vol_ratio > 1.2 and abs(now_pct) < 0.3:
            score -= 5; reasons.append("放量滞涨,资金分歧")
        elif vol_ratio > 1.2 and abs(intraday_chg) < 0.5:
            score -= 3; reasons.append("放量横盘,方向不明")
    elif avg_vol == 0:
        # 没有均量数据，用简单的当前量比
        if vol > 0:
            reasons.append(f"当日量{vol}")

    return max(0, min(100, score)), reasons


def score_to_signal(score):
    """将0-100分数映射为买卖信号"""
    if score >= 75: return "买入"
    if score >= 60: return "增持"
    if score >= 45: return "持有"
    if score >= 30: return "减仓"
    return "卖出"


def assess_capital_flow(code, market):
    """主力资金评分 (0-100) — 基于东方财富资金流数据"""
    if not code:
        return 0, ["暂无资金数据"]

    secid = "1." + code if market == "sh" else "0." + code
    url = ("http://push2.eastmoney.com/api/qt/stock/fflow/daykline/get?"
           f"secid={secid}&fields1=f1,f2,f3,f7&fields2=f51,f52,f53,f54,"
           f"f55,f56,f57,f58,f59,f60,f61,f62,f63")

    try:
        import requests
        r = requests.get(url, timeout=5, headers={"User-Agent": "Mozilla/5.0"})
        data = r.json()
        raw_klines = (data.get("data") or {}).get("klines") or []
        if not raw_klines:
            return 0, ["暂无资金数据"]
    except Exception:
        return 0, ["资金数据获取失败"]

    records = []
    for k in raw_klines[:10]:
        parts = k.split(",")
        if len(parts) >= 13:
            records.append({
                "date": parts[0],
                "main_net": float(parts[1]),   # 主力净流入(元)
                "super_large": float(parts[2]), # 超大单净流入
                "large": float(parts[3]),       # 大单净流入
                "main_pct": float(parts[6]),    # 主力净占比(%)
            })

    if not records:
        return 50, ["资金数据格式异常"]

    score = 50
    reasons = []
    latest = records[0]
    recent = records[:min(5, len(records))]

    # 1. 当日主力净流入额
    main_wan = latest["main_net"] / 1e4
    if main_wan > 5000:
        score += 15
        reasons.append(f"主力净流入{main_wan:.0f}万")
    elif main_wan > 1000:
        score += 8
        reasons.append(f"主力小幅流入{main_wan:.0f}万")
    elif main_wan < -5000:
        score -= 15
        reasons.append(f"主力大幅流出{abs(main_wan):.0f}万")
    elif main_wan < -1000:
        score -= 8
        reasons.append(f"主力小幅流出{abs(main_wan):.0f}万")

    # 2. 累计 N 日净流向
    total_wan = sum(r["main_net"] for r in recent) / 1e4
    if total_wan > 10000 and len(recent) >= 3:
        score += 10
        reasons.append(f"{len(recent)}日累计净流入{total_wan:.0f}万")
    elif total_wan < -10000 and len(recent) >= 3:
        score -= 10
        reasons.append(f"{len(recent)}日累计净流出{abs(total_wan):.0f}万")

    # 3. 连续净流入/流出天数
    same_dir = 1
    for i in range(len(records) - 1):
        if records[i]["main_net"] * records[i + 1]["main_net"] > 0:
            same_dir += 1
        else:
            break
    if latest["main_net"] > 0 and same_dir >= 3:
        score += 8
        reasons.append(f"主力连续{same_dir}日净流入")
    elif latest["main_net"] < 0 and same_dir >= 3:
        score -= 8
        reasons.append(f"主力连续{same_dir}日净流出")

    # 4. 主力净占比
    mpct = latest["main_pct"]
    if mpct > 8:
        score += 7
        reasons.append(f"主力净占比{mpct:.1f}%")
    elif mpct < -8:
        score -= 7
        reasons.append(f"主力净占比{mpct:.1f}%(流出)")


    # 量价关系形态加分
    if klines and len(klines) >= 60:
        try:
            vpr = classify_vp_relationship(klines)
            if vpr['score'] != 0:
                score += vpr['score']
            reasons.append(f"量价{vpr['type']}({vpr['label']})")
        except:
            pass
    # 残差动量
    if len(closes) >= 60:
        try:
            rm = calc_residual_momentum(closes)
            if rm['score'] != 0:
                score += rm['score']
                reasons.append(f"残差动量({rm['score']:+d})")
        except:
            pass
    score = max(0, min(100, score))
    return score, reasons


def make_decision(closes, klines, patterns, sr, sector_ctx=None, quote=None, code=None, market=None):
    """综合决策 — 返回明确买卖信号
    quote: 可选，传入实时行情数据用于分时评分
    """
    trend_score, trend_reasons = assess_trend(closes)
    pat_score, pat_reasons = assess_patterns(patterns)
    level_score, level_reasons = assess_price_level(closes, sr)
    vol_score, vol_reasons = assess_volume(closes, klines)
    sector_score, sector_reasons = assess_sector(sector_ctx)
    intraday_score, intraday_reasons = assess_intraday(quote, closes, klines)
    capital_score, capital_reasons = assess_capital_flow(code, market)

    weights = {
        "trend": 0.23,
        "patterns": 0.17,
        "price_level": 0.15,
        "volume": 0.08,
        "sector": 0.10,
        "intraday": 0.10,
        "capital": 0.17,
    }

    total = (
        trend_score * weights["trend"]
        + pat_score * weights["patterns"]
        + level_score * weights["price_level"]
        + vol_score * weights["volume"]
        + sector_score * weights["sector"]
        + intraday_score * weights["intraday"]
        + capital_score * weights["capital"]
    )
    total = round(max(0, min(100, total)), 1)

    # 信号映射
    signal = score_to_signal(total)
    sub_map = {"买入": "强烈建议买入", "增持": "可逢低加仓", "持有": "继续持有观察", "减仓": "考虑逐步减仓", "卖出": "建议离场回避"}
    color_map = {"买入": "#ff4757", "增持": "#ff6b81", "持有": "#00d2ff", "减仓": "#ffa502", "卖出": "#2ed573"}
    sub = sub_map.get(signal, "继续持有观察")
    color = color_map.get(signal, "#00d2ff")

    # 各方法独立信号
    method_signals = {
        "trend": {"score": trend_score, "signal": score_to_signal(trend_score)},
        "patterns": {"score": pat_score, "signal": score_to_signal(pat_score)},
        "price_level": {"score": level_score, "signal": score_to_signal(level_score)},
        "volume": {"score": vol_score, "signal": score_to_signal(vol_score)},
        "sector": {"score": sector_score, "signal": score_to_signal(sector_score)},
        "intraday": {"score": intraday_score, "signal": score_to_signal(intraday_score)},
        "capital": {"score": capital_score, "signal": score_to_signal(capital_score)},
    }

    # 汇总理由 (每个维度取前2条)
    all_reasons = []
    seen = set()
    for r in (trend_reasons + pat_reasons + level_reasons + vol_reasons
              + sector_reasons + capital_reasons):
        if r not in seen:
            seen.add(r)
            all_reasons.append(r)

    # ML评分（若模型存在则覆盖）
    try:
        from engine.ml_scorer import score as ml_score, is_ready as ml_ready, get_raw_fields
        if ml_ready():
            details_last = details_list[-1] if details_list else {}
            ml_f = {
                'trend': details_last.get('score', 50),
                'patterns': details.get('patterns', {}).get('score', 50),
                'price_level': details.get('price_level', {}).get('score', 50),
                'volume': details.get('volume', {}).get('score', 50),
                'sector': details.get('sector', {}).get('score', 50),
                'intraday': details.get('intraday', {}).get('score', 50),
                'capital': details.get('capital', {}).get('score', 50),
                'total_score': total_score,
                'signal': signal,
            }
            raw_f = get_raw_fields(klines, quote) if klines is not None else None
            ml_s = ml_score(ml_f, raw_f)
            if ml_s is not None:
                blended = int(ml_s * 0.7 + total_score * 0.3)
                total_score = max(0, min(100, blended))
                signal = score_to_signal(total_score)
    except:
        pass
    
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
            "intraday": {"score": intraday_score, "reasons": intraday_reasons, "weight": weights["intraday"]},
            "capital": {"score": capital_score, "reasons": capital_reasons, "weight": weights["capital"]},
        },
        "method_signals": method_signals,
        "reasons": all_reasons[:10] + intraday_reasons[:3],
    }
