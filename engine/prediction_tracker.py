"""预测追踪与回测 — 记录决策、验证胜率、统计准确率"""
import json, os, time

PREDICTIONS_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'predictions')
PREDICTIONS_FILE = os.path.join(PREDICTIONS_DIR, 'predictions.json')
# 15分钟间隔记录时间点: 上午 09:25~11:25, 下午 13:10~15:10
RECORD_TIMES = [
    "09:25","09:40","09:55","10:10","10:25","10:40","10:55","11:10","11:25",
    "13:10","13:25","13:40","13:55","14:10","14:25","14:40","14:55","15:10",
]

# 2026年A股休市日期（非周末的节假日）
TRADING_HOLIDAYS = {
    "2026-01-01", "2026-01-02",
    "2026-02-16", "2026-02-17", "2026-02-18", "2026-02-19", "2026-02-20",
    "2026-04-06",
    "2026-05-01", "2026-05-04", "2026-05-05",
    "2026-06-25", "2026-06-26",
    "2026-10-01", "2026-10-02", "2026-10-05", "2026-10-06", "2026-10-07",
}


def is_trading_day(t=None):
    """判断是否为交易日（非周末、非节假日）"""
    if t is None:
        t = time.localtime()
    if t.tm_wday >= 5:
        return False
    return time.strftime("%Y-%m-%d", t) not in TRADING_HOLIDAYS


def _load():
    os.makedirs(PREDICTIONS_DIR, exist_ok=True)
    if not os.path.exists(PREDICTIONS_FILE):
        return []
    try:
        with open(PREDICTIONS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return []


def _save(data):
    os.makedirs(PREDICTIONS_DIR, exist_ok=True)
    with open(PREDICTIONS_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def is_record_time(hour, minute):
    """判断 (hour, minute) 是否属于记录时间点"""
    for t in RECORD_TIMES:
        h, m = map(int, t.split(':'))
        if hour == h and minute == m:
            return True
    return False


def record_prediction(code, market, name, signal, score, price, record_time=None):
    """记录一条预测（同一股票+同日+同时段去重）
    自动检测信号变化（与前一个时间点对比），存入 signal_change 字段
    record_time: 可选，指定记录时间，不指定则用当前时间
    """
    today = time.strftime("%Y-%m-%d")
    now_time = record_time or time.strftime("%H:%M")

    if now_time not in RECORD_TIMES:
        return

    data = _load()

    # 信号强度映射（用于量化比较）
    SIGNAL_RANK = {"买入": 5, "增持": 4, "持有": 3, "减仓": 2, "卖出": 1}

    # 查找同一股票今天上一个时间点的记录
    prev_signal = None
    prev_score = None
    for r in reversed(data):
        if r.get("date") == today and r.get("code") == code:
            prev_signal = r.get("signal")
            prev_score = r.get("score")
            break

    # 检测信号变化
    signal_change = None
    cur_rank = SIGNAL_RANK.get(signal, 0)
    prev_rank = SIGNAL_RANK.get(prev_signal, 0) if prev_signal else 0
    if prev_signal and prev_signal != signal:
        if cur_rank > prev_rank:
            signal_change = f"信号转强:{prev_signal}→{signal}({prev_score}→{score})"
        elif cur_rank < prev_rank:
            signal_change = f"信号转弱:{prev_signal}→{signal}({prev_score}→{score})"

    for i, r in enumerate(data):
        if r.get("date") == today and r.get("code") == code and r.get("time") == now_time:
            data[i] = {
                "date": today, "time": now_time,
                "code": code, "market": market, "name": name,
                "signal": signal, "score": score, "price": price,
                "verified": False,
            }
            if signal_change:
                data[i]["signal_change"] = signal_change
            _save(data)
            return

    new_record = {
        "date": today, "time": now_time,
        "code": code, "market": market, "name": name,
        "signal": signal, "score": score, "price": price,
        "verified": False,
    }
    if signal_change:
        new_record["signal_change"] = signal_change
    data.append(new_record)
    _save(data)


def verify_predictions(fetch_kline_func):
    """验证所有未验证的预测: 取次日+多日收盘价对比"""
    data = _load()
    if not data:
        return 0

    today = time.strftime("%Y-%m-%d")
    verified_count = 0

    for r in data:
        if r.get("verified"):
            continue

        pred_date = r["date"]
        code = r["code"]
        market = r.get("market", "sh")
        full_code = market + code
        pred_price = r.get("price", 0)

        # 今天的预测：15:10时，先填入今日收盘价作为verify_track起点
        if pred_date == today:
            if pred_price > 0 and not r.get("verify_track"):
                try:
                    klines = fetch_kline_func(full_code, 5)
                    for k in klines:
                        if k["date"] == today:
                            r["verify_track"] = [
                                {"date": pred_date, "close": pred_price},
                                {"date": today, "close": k["close"]},
                            ]
                            break
                except:
                    pass
            continue

        if pred_price <= 0:
            r["verified"] = True
            r["correct"] = False
            r["next_close"] = 0
            r["next_change_pct"] = 0
            r["verify_date"] = today
            r["verify_track"] = [{"date": pred_date, "close": 0}]
            verified_count += 1
            continue

        try:
            klines = fetch_kline_func(full_code, 30)
            if not klines or len(klines) < 2:
                continue

            pred_idx = None
            for i, k in enumerate(klines):
                if k["date"] == pred_date:
                    pred_idx = i
                    break

            if pred_idx is None:
                continue

            later_klines = [k for k in klines[pred_idx+1:] if k["date"] != pred_date]

            track = [{"date": pred_date, "close": pred_price}]
            for k in later_klines:
                track.append({"date": k["date"], "close": k["close"]})

            if len(track) < 2:
                continue

            next_close = track[1]["close"]
            change_pct = (next_close - pred_price) / pred_price * 100

            signal = r.get("signal", "")
            if signal in ("买入", "增持"):
                correct = change_pct > 0
            elif signal in ("卖出", "减仓"):
                correct = change_pct < 0
            else:
                correct = None

            r["next_close"] = round(next_close, 2)
            r["next_change_pct"] = round(change_pct, 2)
            r["correct"] = correct
            r["verified"] = True
            r["verify_date"] = today
            r["verify_track"] = track
            verified_count += 1

        except:
            continue

    _save(data)
    return verified_count


def update_prediction_tracks(fetch_kline_func):
    """增量更新已验证记录的verify_track，追加新的后续交易日数据"""
    data = _load()
    today = time.strftime("%Y-%m-%d")
    updated = 0

    for r in data:
        if not r.get("verified"):
            continue
        track = r.get("verify_track", [])
        if not track:
            continue

        last_track_date = track[-1]["date"]
        if last_track_date == today:
            continue

        code = r["code"]
        market = r.get("market", "sh")
        full_code = market + code

        try:
            klines = fetch_kline_func(full_code, 30)
            if not klines:
                continue

            collecting = False
            new_days = []
            for k in klines:
                if k["date"] == last_track_date:
                    collecting = True
                    continue
                if collecting and k["date"] != last_track_date:
                    new_days.append({"date": k["date"], "close": k["close"]})

            if new_days:
                r["verify_track"] = track + new_days
                updated += 1

        except:
            continue

    if updated:
        _save(data)
    return updated


def get_signal_stats():
    """按信号类型统计准确率"""
    data = _load()
    verified = [r for r in data if r.get("verified") and r.get("correct") is not None]

    stats = {}
    total_correct = 0
    total_count = 0

    for r in verified:
        sig = r.get("signal", "未知")
        if sig not in stats:
            stats[sig] = {"correct": 0, "total": 0}
        stats[sig]["total"] += 1
        total_count += 1
        if r["correct"]:
            stats[sig]["correct"] += 1
            total_correct += 1

    result = {}
    for sig, s in stats.items():
        result[sig] = {
            "correct": s["correct"],
            "total": s["total"],
            "accuracy": round(s["correct"] / s["total"] * 100, 1) if s["total"] > 0 else 0,
        }

    return {
        "by_signal": result,
        "total_correct": total_correct,
        "total_count": total_count,
        "overall_accuracy": round(total_correct / total_count * 100, 1) if total_count > 0 else 0,
        "total_predictions": len(data),
        "pending_verify": sum(1 for r in data if not r.get("verified")),
    }


def get_stock_stats(code):
    """单只股票的预测历史"""
    data = _load()
    records = [r for r in data if r.get("code") == code]
    if not records:
        return {"code": code, "records": [], "accuracy": 0, "total": 0}

    verified = [r for r in records if r.get("verified") and r.get("correct") is not None]
    correct_count = sum(1 for r in verified if r["correct"])
    total = len(verified)

    return {
        "code": code,
        "records": sorted(records, key=lambda x: (x.get("date", ""), x.get("time", ""))),
        "accuracy": round(correct_count / total * 100, 1) if total > 0 else 0,
        "correct": correct_count,
        "total": total,
    }


def get_recent_results(days=7):
    """近N天的验证结果，按股票+日期分组展示各时间点"""
    data = _load()
    today = time.strftime("%Y-%m-%d")
    # 取有verify_track的记录，或今天的记录（收盘后15:10才填verify_track，但白天就可见）
    visible = [r for r in data if r.get("verify_track") or r.get("date") == today]

    dates = sorted(set(r["date"] for r in visible), reverse=True)[:days]

    # 计算各股票的历史准确率
    stock_stats = {}
    for r in data:
        code = r.get("code")
        if code not in stock_stats:
            stock_stats[code] = {"correct": 0, "total": 0}
        if r.get("verified") and r.get("correct") is not None:
            stock_stats[code]["total"] += 1
            if r["correct"]:
                stock_stats[code]["correct"] += 1

    result = []
    for date in dates:
        day_records = [r for r in visible if r["date"] == date]
        stocks = {}
        for r in day_records:
            code = r["code"]
            if code not in stocks:
                ss = stock_stats.get(code, {})
                acc = round(ss.get("correct", 0) / ss.get("total", 1) * 100, 1) if ss.get("total", 0) > 0 else 0
                stocks[code] = {
                    "code": code, "name": r.get("name", code), "records": [],
                    "accuracy": acc, "accuracy_total": ss.get("total", 0),
                }
            stocks[code]["records"].append({
                "time": r.get("time", ""),
                "signal": r.get("signal", ""),
                "score": r.get("score", 0),
                "price": r.get("price", 0),
                "next_change_pct": r.get("next_change_pct"),
                "correct": r.get("correct"),
                "verify_track": r.get("verify_track", []),
                "signal_change": r.get("signal_change"),
            })
        for s in stocks.values():
            s["records"].sort(key=lambda x: x.get("time", ""))

        result.append({
            "date": date,
            "stocks": list(stocks.values()),
        })

    return result


def get_signal_performance():
    """按信号类型统计各持有期的平均收益率和胜率
    从 verify_track 中提取 +1, +3, +5, +10 天的涨跌幅
    """
    data = _load()
    verified = [r for r in data if r.get("verify_track") and len(r["verify_track"]) >= 2]

    # offsets 天数偏移
    offsets = [1, 3, 5, 10]

    stats = {}  # {signal: {offsets: {return: [], correct: []}, total: N}}
    for r in verified:
        sig = r.get("signal", "未知")
        if sig not in stats:
            stats[sig] = {"total": 0, "offsets": {o: {"returns": [], "correct": 0, "count": 0} for o in offsets}}
        stats[sig]["total"] += 1

        track = r["verify_track"]
        pred_price = track[0]["close"]
        if pred_price <= 0:
            continue

        for o in offsets:
            if len(track) > o:
                cur_close = track[o]["close"]
                ret = (cur_close - pred_price) / pred_price * 100
                stats[sig]["offsets"][o]["returns"].append(ret)
                stats[sig]["offsets"][o]["count"] += 1
                # 判断对错（与预测信号方向一致）
                if sig in ("买入", "增持"):
                    if ret > 0:
                        stats[sig]["offsets"][o]["correct"] += 1
                elif sig in ("卖出", "减仓"):
                    if ret < 0:
                        stats[sig]["offsets"][o]["correct"] += 1

    result = {}
    for sig, sdata in stats.items():
        sig_result = {"total": sdata["total"], "offsets": {}}
        for o, odata in sdata["offsets"].items():
            if odata["count"] == 0:
                continue
            avg_ret = sum(odata["returns"]) / odata["count"]
            win_rate = odata["correct"] / odata["count"] * 100 if odata["count"] > 0 else 0
            sig_result["offsets"][o] = {
                "count": odata["count"],
                "avg_return": round(avg_ret, 2),
                "win_rate": round(win_rate, 1),
            }
        result[sig] = sig_result

    # 今日信号变化汇总
    today = time.strftime("%Y-%m-%d")
    today_records = [r for r in data if r.get("date") == today]
    signal_changes = []
    for r in today_records:
        sc = r.get("signal_change", "")
        if sc:
            signal_changes.append({
                "code": r.get("code", ""),
                "name": r.get("name", ""),
                "time": r.get("time", ""),
                "signal": r.get("signal", ""),
                "score": r.get("score", 0),
                "change": sc,
                "price": r.get("price", 0),
            })

    return {
        "by_signal": result,
        "today_changes": signal_changes,
        "total_verified": sum(1 for r in verified if r.get("verified")),
    }
