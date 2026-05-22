"""预测追踪与回测 — 记录决策、验证胜率、统计准确率"""
import json, os, time

PREDICTIONS_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'predictions')
PREDICTIONS_FILE = os.path.join(PREDICTIONS_DIR, 'predictions.json')
# 15分钟间隔记录时间点: 上午 09:25~11:25, 下午 13:10~15:10
RECORD_TIMES = [
    "09:25","09:40","09:55","10:10","10:25","10:40","10:55","11:10","11:25",
    "13:10","13:25","13:40","13:55","14:10","14:25","14:40","14:55","15:10",
]


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
    record_time: 可选，指定记录时间，不指定则用当前时间
    """
    today = time.strftime("%Y-%m-%d")
    now_time = record_time or time.strftime("%H:%M")

    if now_time not in RECORD_TIMES:
        return

    data = _load()
    for i, r in enumerate(data):
        if r.get("date") == today and r.get("code") == code and r.get("time") == now_time:
            data[i] = {
                "date": today, "time": now_time,
                "code": code, "market": market, "name": name,
                "signal": signal, "score": score, "price": price,
                "verified": False,
            }
            _save(data)
            return

    data.append({
        "date": today, "time": now_time,
        "code": code, "market": market, "name": name,
        "signal": signal, "score": score, "price": price,
        "verified": False,
    })
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

    result = []
    for date in dates:
        day_records = [r for r in visible if r["date"] == date]
        stocks = {}
        for r in day_records:
            code = r["code"]
            if code not in stocks:
                stocks[code] = {"code": code, "name": r.get("name", code), "records": []}
            stocks[code]["records"].append({
                "time": r.get("time", ""),
                "signal": r.get("signal", ""),
                "score": r.get("score", 0),
                "price": r.get("price", 0),
                "next_change_pct": r.get("next_change_pct"),
                "correct": r.get("correct"),
                "verify_track": r.get("verify_track", []),
            })
        for s in stocks.values():
            s["records"].sort(key=lambda x: x.get("time", ""))

        result.append({
            "date": date,
            "stocks": list(stocks.values()),
        })

    return result
