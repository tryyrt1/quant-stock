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


def record_prediction(code, market, name, signal, score, price, record_time=None, methods=None):
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
            if methods:
                data[i]["methods"] = methods
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
    if methods:
        new_record["methods"] = methods
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

            # 当日（分时）涨跌幅: 预测价 → 当日收盘价
            same_day_close = klines[pred_idx]["close"]
            same_day_change_pct = (same_day_close - pred_price) / pred_price * 100 if pred_price > 0 else 0

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
            r["same_day_change_pct"] = round(same_day_change_pct, 2)  # 当日分时验证
            verified_count += 1

            # 验证各独立方法（共用同一个 change_pct）
            methods = r.get("methods", {})
            if methods:
                verified_methods = {}
                for mkey, minfo in methods.items():
                    # 保留原始 score/signal，补充 verified/correct
                    orig_score = minfo.get("score", 50)
                    orig_signal = minfo.get("signal", "持有")
                    if orig_signal in ("买入", "增持"):
                        mcorrect = change_pct > 0
                    elif orig_signal in ("卖出", "减仓"):
                        mcorrect = change_pct < 0
                    else:
                        mcorrect = None
                    verified_methods[mkey] = {
                        "score": orig_score,
                        "signal": orig_signal,
                        "verified": True,
                        "correct": mcorrect,
                    }
                r["methods"] = verified_methods

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
                "methods": r.get("methods", {}),
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


def auto_diagnose():
    """自动回测诊断: 分析已验证预测，找出最准的信号方法并给出建议"""
    data = _load()
    # 只取已验证的记录
    verified = [r for r in data if r.get("verified") and r.get("correct") is not None]

    if not verified:
        return {
            "status": "no_data",
            "message": "暂无已验证数据，需等待至少一个交易日的验证周期",
            "signals": [],
            "best_signal": None,
            "worst_signal": None,
            "recommendations": ["等待数据积累，至少需要一个交易日后才能生成诊断报告"],
            "total_samples": 0,
        }

    # 按信号统计
    sig_stats = {}
    for r in verified:
        sig = r.get("signal", "未知")
        if sig not in sig_stats:
            sig_stats[sig] = {"correct": 0, "total": 0, "returns": []}
        sig_stats[sig]["total"] += 1
        sig_stats[sig]["returns"].append(r.get("next_change_pct", 0))
        if r["correct"]:
            sig_stats[sig]["correct"] += 1

    # 按股票统计
    stock_stats = {}
    for r in verified:
        code = r.get("code", "")
        name = r.get("name", code)
        if code not in stock_stats:
            stock_stats[code] = {"code": code, "name": name, "correct": 0, "total": 0, "returns": []}
        stock_stats[code]["total"] += 1
        stock_stats[code]["returns"].append(r.get("next_change_pct", 0))
        if r["correct"]:
            stock_stats[code]["correct"] += 1

    # 构建信号分析结果
    signals = []
    for sig, s in sig_stats.items():
        avg_ret = sum(s["returns"]) / len(s["returns"]) if s["returns"] else 0
        win_rate = round(s["correct"] / s["total"] * 100, 1) if s["total"] > 0 else 0
        signals.append({
            "signal": sig,
            "accuracy": win_rate,
            "correct": s["correct"],
            "total": s["total"],
            "avg_return": round(avg_ret, 2),
        })

    signals.sort(key=lambda x: x["accuracy"], reverse=True)

    # 找出最佳和最差
    best = signals[0] if signals else None
    worst = signals[-1] if len(signals) > 1 else None

    # 按股票分析准确率
    stocks_rank = []
    for code, s in stock_stats.items():
        win_rate = round(s["correct"] / s["total"] * 100, 1) if s["total"] > 0 else 0
        avg_ret = sum(s["returns"]) / len(s["returns"]) if s["returns"] else 0
        stocks_rank.append({
            "code": s["code"],
            "name": s["name"],
            "accuracy": win_rate,
            "correct": s["correct"],
            "total": s["total"],
            "avg_return": round(avg_ret, 2),
        })
    stocks_rank.sort(key=lambda x: x["accuracy"], reverse=True)

    # 生成建议
    recommendations = []
    if best and best["accuracy"] >= 55:
        recommendations.append(
            f"✅ 最佳信号「{best['signal']}」胜率{best['accuracy']}%，"
            f"均收益{best['avg_return']:+.2f}%（{best['total']}样本），建议优先参考"
        )
    elif best and best["accuracy"] >= 45:
        recommendations.append(
            f"📊 最佳信号「{best['signal']}」胜率{best['accuracy']}%，"
            f"效果中等，建议结合大盘环境使用"
        )
    else:
        recommendations.append(
            f"📈 当前样本有限（共{len(verified)}条），最佳信号胜率{best['accuracy'] if best else 0}%，"
            f"需要更多数据积累才能可靠评估"
        )

    if worst and worst != best and worst["accuracy"] < 45:
        recommendations.append(
            f"⚠️ 信号「{worst['signal']}」胜率仅{worst['accuracy']}%，"
            f"均收益{worst['avg_return']:+.2f}%（{worst['total']}样本），建议谨慎使用"
        )

    # 总体统计
    all_returns = [r.get("next_change_pct", 0) for r in verified if r.get("next_change_pct") is not None]
    total_correct = sum(1 for r in verified if r["correct"])
    total_samples = len(verified)
    overall_acc = round(total_correct / total_samples * 100, 1) if total_samples > 0 else 0
    overall_avg_ret = round(sum(all_returns) / len(all_returns), 2) if all_returns else 0

    # 按日期统计趋势
    daily = {}
    for r in sorted(verified, key=lambda x: x.get("date", "")):
        d = r.get("date", "")
        if d not in daily:
            daily[d] = {"correct": 0, "total": 0}
        daily[d]["total"] += 1
        if r["correct"]:
            daily[d]["correct"] += 1
    daily_trend = []
    for d, s in daily.items():
        daily_trend.append({
            "date": d,
            "accuracy": round(s["correct"] / s["total"] * 100, 1) if s["total"] > 0 else 0,
            "correct": s["correct"],
            "total": s["total"],
        })

    return {
        "status": "ok",
        "total_samples": total_samples,
        "total_correct": total_correct,
        "overall_accuracy": overall_acc,
        "overall_avg_return": overall_avg_ret,
        "best_signal": best,
        "worst_signal": worst if worst != best else None,
        "signals": signals,
        "top_stocks": stocks_rank[:10],
        "worst_stocks": stocks_rank[-5:] if len(stocks_rank) > 5 else [],
        "daily_trend": daily_trend[-10:],
        "recommendations": recommendations,
        "message": f"基于{total_samples}条已验证预测的分析报告（准确率{overall_acc}%，均收益{overall_avg_ret:+.2f}%）",
    }


METHOD_NAMES = {
    "trend": "趋势法",
    "patterns": "形态法",
    "price_level": "价位法",
    "volume": "量能法",
    "sector": "板块法",
    "intraday": "分时法",
    "capital": "资金法",
}


def get_method_multi_offset_stats():
    """统计各方法在不同时间偏移上的准确率
    偏移: 0=当日分时, 1=+1日, 2=+2日, 3=+3日, 5=+5日, 10=+10日, 15=+15日, 20=+20日, 30=+30日
    返回: {method_key: {name, offset: {accuracy, correct, total, avg_return}}}
    """
    data = _load()
    # 只取已验证且含 methods 的记录
    records = [r for r in data if r.get("verified") and r.get("methods") and r.get("verify_track")]

    offsets = [0, 1, 2, 3, 5, 10, 15, 20, 30]

    # 初始化统计
    stats = {}
    for mkey in METHOD_NAMES:
        stats[mkey] = {"name": METHOD_NAMES[mkey], "total_records": 0}
        for o in offsets:
            stats[mkey][o] = {"correct": 0, "total": 0, "returns": []}

    for r in records:
        methods = r.get("methods", {})
        track = r.get("verify_track", [])
        pred_price = track[0]["close"] if track else 0
        same_day_pct = r.get("same_day_change_pct")

        if pred_price <= 0:
            continue

        for mkey, minfo in methods.items():
            if mkey not in stats:
                continue
            # 只统计已验证的方法
            if not minfo.get("verified"):
                continue
            stats[mkey]["total_records"] += 1
            msig = minfo.get("signal", "持有")

            for o in offsets:
                if o == 0:
                    # 当日分时: 使用 same_day_change_pct
                    if same_day_pct is not None:
                        ret = same_day_pct
                    else:
                        continue
                else:
                    # 从 verify_track 取对应偏移
                    if len(track) > o:
                        ret = (track[o]["close"] - pred_price) / pred_price * 100
                    else:
                        continue

                # 持有/中性信号不纳入准确率统计（避免分母膨胀）
                if msig not in ("买入", "增持", "卖出", "减仓"):
                    continue

                stats[mkey][o]["returns"].append(ret)
                stats[mkey][o]["total"] += 1

                if msig in ("买入", "增持"):
                    if ret > 0:
                        stats[mkey][o]["correct"] += 1
                elif msig in ("卖出", "减仓"):
                    if ret < 0:
                        stats[mkey][o]["correct"] += 1

    # 格式化结果
    result = {}
    for mkey, sdata in stats.items():
        if sdata["total_records"] == 0:
            continue
        mresult = {"name": sdata["name"], "total_records": sdata["total_records"], "offsets": {}}
        for o in offsets:
            odata = sdata[o]
            if odata["total"] == 0:
                continue
            avg_ret = sum(odata["returns"]) / len(odata["returns"])
            accuracy = round(odata["correct"] / odata["total"] * 100, 1) if odata["total"] > 0 else 0
            mresult["offsets"][o] = {
                "accuracy": accuracy,
                "correct": odata["correct"],
                "total": odata["total"],
                "avg_return": round(avg_ret, 2),
            }
        if mresult["offsets"]:
            result[mkey] = mresult

    # 添加综合法（复合信号）的对比
    composite = {"name": "综合法", "total_records": 0, "offsets": {}}
    verified_all = [r for r in data if r.get("verified") and r.get("verify_track") and r.get("correct") is not None]
    for r in verified_all:
        track = r.get("verify_track", [])
        pred_price = track[0]["close"] if track else 0
        same_day_pct = r.get("same_day_change_pct")
        if pred_price <= 0:
            continue
        signal = r.get("signal", "持有")
        composite["total_records"] += 1
        for o in offsets:
            if o == 0:
                if same_day_pct is not None:
                    ret = same_day_pct
                else:
                    continue
            else:
                if len(track) > o:
                    ret = (track[o]["close"] - pred_price) / pred_price * 100
                else:
                    continue
            if o not in composite["offsets"]:
                composite["offsets"][o] = {"correct": 0, "total": 0, "returns": []}
            composite["offsets"][o]["returns"].append(ret)
            composite["offsets"][o]["total"] += 1
            if signal in ("买入", "增持"):
                if ret > 0:
                    composite["offsets"][o]["correct"] += 1
            elif signal in ("卖出", "减仓"):
                if ret < 0:
                    composite["offsets"][o]["correct"] += 1
    if composite["total_records"] > 0:
        co_result = {"name": "综合法", "total_records": composite["total_records"], "offsets": {}}
        for o, odata in composite["offsets"].items():
            if odata["total"] == 0:
                continue
            avg_ret = sum(odata["returns"]) / len(odata["returns"])
            accuracy = round(odata["correct"] / odata["total"] * 100, 1) if odata["total"] > 0 else 0
            co_result["offsets"][o] = {
                "accuracy": accuracy,
                "correct": odata["correct"],
                "total": odata["total"],
                "avg_return": round(avg_ret, 2),
            }
        if co_result["offsets"]:
            result["composite"] = co_result

    return result


def get_stock_method_snapshot(code):
    """返回指定股票最新预测记录的 methods 快照 + 多偏移统计"""
    data = _load()
    records = [r for r in data if r.get("code") == code and r.get("methods")]
    if not records:
        return {"code": code, "has_methods": False}

    latest = sorted(records, key=lambda x: (x.get("date", ""), x.get("time", "")))[-1]

    methods = latest.get("methods", {})
    track = latest.get("verify_track", [])
    pred_price = track[0]["close"] if track else 0

    snapshot = {
        "code": code,
        "name": latest.get("name", code),
        "date": latest.get("date", ""),
        "time": latest.get("time", ""),
        "signal": latest.get("signal", ""),
        "score": latest.get("score", 0),
        "price": latest.get("price", 0),
        "verified": latest.get("verified", False),
        "methods": {},
    }

    for mkey, minfo in methods.items():
        snapshot["methods"][mkey] = {
            "score": minfo.get("score", 50),
            "signal": minfo.get("signal", "持有"),
            "verified": minfo.get("verified", False),
            "correct": minfo.get("correct"),
        }

    # 如果已验证且有 track，计算多偏移表现
    if latest.get("verified") and track and pred_price > 0:
        same_day_pct = latest.get("same_day_change_pct")
        offsets = [0, 1, 2, 3, 5, 10, 15, 20, 30]
        multi = {}
        for o in offsets:
            if o == 0:
                if same_day_pct is not None:
                    multi[o] = {"return": round(same_day_pct, 2)}
            else:
                if len(track) > o:
                    ret = (track[o]["close"] - pred_price) / pred_price * 100
                    multi[o] = {"return": round(ret, 2)}
        if multi:
            snapshot["multi_offset"] = multi

    return snapshot


# ─── 自选股次日预测系统 ───
NEXTDAY_FILE = os.path.join(PREDICTIONS_DIR, 'nextday.json')

def _load_nextday():
    os.makedirs(PREDICTIONS_DIR, exist_ok=True)
    if not os.path.exists(NEXTDAY_FILE):
        return []
    try:
        with open(NEXTDAY_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return []

def _save_nextday(data):
    os.makedirs(PREDICTIONS_DIR, exist_ok=True)
    with open(NEXTDAY_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def record_nextday_prediction(watchlist, fetch_kline_func=None):
    """收盘后(15:01)记录次日方向预测"""
    today = time.strftime('%Y-%m-%d')
    data = _load_nextday()

    # 删除今日已有记录（重新写入）
    data = [r for r in data if not (r.get('date') == today)]

    from engine.decision import make_decision
    from engine.indicators import calc_support_resistance
    from engine.patterns import scan_patterns

    recorded = 0
    for s in watchlist:
        try:
            code, market = s['code'], s['market']
            k = fetch_kline_func(market + code, 120) if fetch_kline_func else []
            if len(k) < 60:
                continue
            closes = [x['close'] for x in k]
            sr = calc_support_resistance(k)
            pats = scan_patterns({market + code: k})
            patterns = pats.get(market + code, [])
            decision = make_decision(closes, k, patterns, sr, None, None, code=code, market=market)
            sig = decision.get('signal', '持有')
            sc = decision.get('score', 50)
            direction = '涨' if sig in ('买入', '增持') else '跌' if sig in ('卖出', '减仓') else (closes[-1] > closes[-2] and '涨' or '跌')
            confidence = int(max(abs(sc - 50) * 2, 55)) if sig != '持有' else 55

            data.append({
                'date': today, 'code': code, 'market': market,
                'name': s.get('name', code),
                'direction': direction, 'confidence': confidence,
                'signal': sig, 'score': sc,
                'price': closes[-1] if closes else 0,
                'verified': False, 'correct': None,
            })
            recorded += 1
        except:
            pass

    _save_nextday(data)
    return recorded

def verify_nextday_predictions(fetch_kline_func):
    """验证昨日自选股次日预测"""
    today = time.strftime('%Y-%m-%d')
    data = _load_nextday()
    verified = 0

    for r in data:
        if r.get('verified'):
            continue
        pred_date = r.get('date', '')
        if pred_date == today:
            continue  # 今天的预测还没到验证时间

        code = r['code']
        market = r.get('market', 'sh')
        try:
            klines = fetch_kline_func(market + code, 10)
            if not klines or len(klines) < 2:
                continue

            pred_price = r.get('price', 0)
            if pred_price <= 0:
                continue

            # 找到预测日期下一个交易日的收盘价
            for i, k in enumerate(klines):
                if k['date'] == pred_date and i + 1 < len(klines):
                    next_close = klines[i + 1]['close']
                    next_change = (next_close - pred_price) / pred_price * 100
                    direction = r.get('direction', '涨')
                    correct = (next_change > 0 and direction == '涨') or (next_change < 0 and direction == '跌')
                    r['verified'] = True
                    r['correct'] = correct
                    r['next_close'] = round(next_close, 2)
                    r['next_change_pct'] = round(next_change, 2)
                    verified += 1
                    break
        except:
            continue

    if verified:
        _save_nextday(data)
    return verified

def get_nextday_stats():
    """返回自选股次日预测统计，含个股独立准确率"""
    data = _load_nextday()
    today = time.strftime('%Y-%m-%d')
    today_pred = [r for r in data if r.get('date') == today]
    verified = [r for r in data if r.get('verified') and r.get('correct') is not None]
    correct_count = sum(1 for r in verified if r['correct'])
    total = len(verified)

    stock_stats = {}
    for r in data:
        if not r.get('verified') or r.get('correct') is None:
            continue
        code = r['code']
        if code not in stock_stats:
            stock_stats[code] = {'correct': 0, 'total': 0, 'name': r.get('name', code)}
        stock_stats[code]['total'] += 1
        if r['correct']:
            stock_stats[code]['correct'] += 1
    for code, s in stock_stats.items():
        s['accuracy'] = round(s['correct'] / s['total'] * 100, 1) if s['total'] > 0 else 0

    return {
        'today_predictions': [{
            'code': r['code'], 'name': r.get('name', r['code']),
            'direction': r.get('direction'),
            'signal': r.get('signal'), 'score': r.get('score'),
        } for r in today_pred],
        'stock_stats': stock_stats,
        'correct': correct_count,
        'total': total,
        'accuracy': round(correct_count / total * 100, 1) if total > 0 else 0,
    }
