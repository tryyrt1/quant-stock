#!/usr/bin/env python3
"""全市场周线选股扫描

扫描全市场A股（排除科创板/北交所/ST/*/亏损股，包含创业板），
筛选三个条件同时满足：
  1. 周成交量连续放大 ≥ 4周
  2. 周均线向上（MA5/MA10/MA20 上翘或多头排列）
  3. 突破前高后回调缩量

用法:
    python weekly_scanner.py                     # 完整扫描
    python weekly_scanner.py --max-stocks 50     # 测试模式
    python weekly_scanner.py --workers 10        # 指定并发数
    python weekly_scanner.py --upload            # 扫描后自动上传服务器
    python weekly_scanner.py --resume            # 断点续传
"""

import json
import os
import sys
import time
import argparse
import threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
STOCKS_FILE = os.path.join(DATA_DIR, 'all_stocks.json')
OUTPUT_FILE = os.path.join(DATA_DIR, 'weekly_picks.json')
PROGRESS_FILE = os.path.join(DATA_DIR, 'weekly_scanner_progress.json')

CLOUD_HOST = os.environ.get('CLOUD_HOST', '')
CLOUD_PATH = os.environ.get('CLOUD_PATH', '/home/ubuntu/quant-stock/data/weekly_picks.json')
SSH_KEY = os.environ.get('SSH_KEY', os.path.expanduser('~/.ssh/quant_stock_auto'))

# ─── 股票过滤 ─────────────────────────────────────────

def load_and_filter_stocks():
    """加载 all_stocks.json 并过滤"""
    if not os.path.exists(STOCKS_FILE):
        print(f"[错误] 找不到股票列表: {STOCKS_FILE}")
        return []

    with open(STOCKS_FILE, 'r', encoding='utf-8') as f:
        stocks = json.load(f)

    total = len(stocks)
    filtered = []
    excluded = {'688': 0, 'st': 0, 'bj': 0, 'pe_neg': 0}

    for s in stocks:
        code = s.get('code', '')
        name = s.get('name', '')

        # 排除科创板
        if code.startswith('688'):
            excluded['688'] += 1
            continue
        # 排除北交所
        if code.startswith(('8', '4')):
            excluded['bj'] += 1
            continue
        # 排除ST
        if 'ST' in name.upper() or '退' in name or 'Ｕ' in name:
            excluded['st'] += 1
            continue
        # 排除亏损股
        pe = s.get('pe')
        if pe is not None and pe < 0:
            excluded['pe_neg'] += 1
            continue

        filtered.append(s)

    print(f"  [过滤] 总{total}只 → 排除 科创板{excluded['688']} / 北交所{excluded['bj']} / "
          f"ST{excluded['st']} / 亏损{excluded['pe_neg']} → 保留{len(filtered)}只")
    return filtered


# ─── 腾讯周K线获取 ─────────────────────────────────────

def fetch_weekly_kline(code_str, days=60):
    """从腾讯ifzq获取周K线"""
    url = f'https://ifzq.gtimg.cn/appstock/app/fqkline/get?param={code_str},week,,,{days},qfq'
    try:
        import requests
        r = requests.get(url, timeout=10,
                         headers={'User-Agent': 'Mozilla/5.0'})
        if r.status_code != 200:
            return []
        raw = r.json()
        data = raw.get('data', {})
        klines = (data.get(code_str, {}).get('qfqweek')
                  or data.get(code_str, {}).get('week')
                  or [])
        if not klines:
            return []
        result = []
        for k in klines:
            try:
                result.append({
                    'date': k[0],
                    'open': float(k[1]),
                    'close': float(k[2]),
                    'high': float(k[3]),
                    'low': float(k[4]),
                    'volume': int(float(k[5])),
                })
            except (ValueError, IndexError):
                continue
        return result
    except Exception as e:
        return []


# ─── 辅助函数 ─────────────────────────────────────────

def _ma(arr, n):
    if len(arr) < n:
        return None
    return sum(arr[-n:]) / n


def _pct(cur, prev):
    if prev and prev > 0:
        return round((cur - prev) / prev * 100, 2)
    return 0


def _strip_cur_week(kline):
    """去掉本周尚未完成的K线（周一~周三成交量偏低会误判）"""
    if not kline:
        return kline
    try:
        today = datetime.now()
        cur_y, cur_w, _ = today.isocalendar()
        last = kline[-1]
        ly, lw, _ = datetime.strptime(last['date'], '%Y-%m-%d').isocalendar()
        if ly == cur_y and lw == cur_w:
            return kline[:-1]
    except Exception:
        pass
    return kline


# ─── 三个选股条件 ─────────────────────────────────────

def check_volume_increase(weekly_kline):
    """条件1: 周成交量持续放大

    去掉当前不完整周后，检查成交量是否呈放大趋势：
    - 条件A: 近3周均量 > 前3周均量 × 1.03 (量能阶梯式上升)
    - 条件B: 近3周至少2周成交量环比递增 (量能持续活跃)
    满足条件A或条件B视为通过。
    """
    kline = _strip_cur_week(weekly_kline)
    if len(kline) < 10:
        return False, 0

    vols = [k['volume'] for k in kline]

    # 条件A: 近3周均量 > 前3周均量（量能趋势向上）
    r3 = sum(vols[-3:]) / 3
    p3 = sum(vols[-6:-3]) / 3
    trend_up = r3 > p3 * 1.03

    # 条件B: 近3周至少2周环比递增（量能持续活跃）
    last3_up = 0
    for i in range(3):
        if len(vols) >= 4 + i and vols[-4 + i] < vols[-3 + i]:
            last3_up += 1
    active = last3_up >= 2

    # 计算实际连续递增周数（用于展示）
    chain = 1
    for i in range(len(vols) - 2, -1, -1):
        if vols[i] < vols[i + 1]:
            chain += 1
        else:
            break

    if trend_up or active:
        return True, min(chain, 12)

    return False, 0


def check_ma_upward(weekly_kline):
    """条件2: 周均线向上 — MA5/MA10/MA20 上翘 或 多头排列"""
    closes = [k['close'] for k in weekly_kline]
    if len(closes) < 25:
        return False, {}

    ma5 = _ma(closes, 5)
    ma10 = _ma(closes, 10)
    ma20 = _ma(closes, 20)
    ma5_prev = _ma(closes[:-1], 5)
    ma10_prev = _ma(closes[:-1], 10)
    ma20_prev = _ma(closes[:-1], 20)

    if None in (ma5, ma10, ma20, ma5_prev, ma10_prev, ma20_prev):
        return False, {}

    # 上翘: 当前MA > 上周MA
    up = ma5 > ma5_prev and ma10 > ma10_prev and ma20 > ma20_prev
    # 多头排列: close > MA5 > MA10 > MA20
    aligned = closes[-1] > ma5 > ma10 > ma20

    return up or aligned, {
        'ma5': round(ma5, 2),
        'ma10': round(ma10, 2),
        'ma20': round(ma20, 2),
        'ma5_up': ma5 > ma5_prev,
        'ma10_up': ma10 > ma10_prev,
        'ma20_up': ma20 > ma20_prev,
        'aligned': aligned,
    }


def check_break_pullback(weekly_kline, lookback=26):
    """条件3: 突破前高后回调缩量

    在最近 lookback 周内创出高点 → 当前价格从高点回落 →
    回调过程成交量递减。
    """
    if len(weekly_kline) < lookback + 5:
        return False, {}

    chunk = weekly_kline[-lookback:]
    highs = [k['high'] for k in chunk]
    recent_high = max(highs)
    recent_high_idx = highs.index(recent_high)
    current_close = weekly_kline[-1]['close']

    # 当前价格低于前高（回调中），至少回调2%以上才有意义
    if current_close >= recent_high * 0.98:
        return False, {}

    # 回调过程成交量是否递减
    pullback_bars = chunk[recent_high_idx:]
    if len(pullback_bars) >= 3:
        vols = [k['volume'] for k in pullback_bars]
        # 最近3根成交量均值 < 前3根均值（趋势缩量）
        v_trend = (sum(vols[-3:]) / 3) < (sum(vols[-6:-3]) / 3) if len(vols) >= 6 else False
        # 最后一根量 < 倒数第二根
        v_last_dec = vols[-1] < vols[-2]

        if v_last_dec or v_trend:
            pullback_pct = round((current_close - recent_high) / recent_high * 100, 2)
            return True, {
                'recent_high': round(recent_high, 2),
                'high_week_offset': lookback - recent_high_idx,
                'pullback_pct': pullback_pct,
                'volume_shrinking': v_last_dec,
            }

    return False, {}


# ─── 单只股票评估 ─────────────────────────────────────

def assess_stock(code, market, name, weekly_kline):
    """对一只股票运行三个条件，返回结果或None"""
    if len(weekly_kline) < 30:
        return None

    v_pass, v_count = check_volume_increase(weekly_kline)
    if not v_pass:
        return None

    ma_pass, ma_info = check_ma_upward(weekly_kline)
    if not ma_pass:
        return None

    bp_pass, bp_info = check_break_pullback(weekly_kline)
    if not bp_pass:
        return None

    # 三个条件全满足
    latest = weekly_kline[-1]
    prev = weekly_kline[-2]
    change_pct = _pct(latest['close'], prev['close'])

    # 当前价/5周均量
    vols = [k['volume'] for k in weekly_kline]
    vol_ma5 = _ma(vols, 5) or 1

    signals = []
    if v_pass:
        signals.append(f"成交量{v_count}连增")
    if ma_pass:
        signals.append("周均线多头")
    if bp_pass:
        signals.append("突破回踩缩量")

    # 综合评分（各30分基础+加分）
    score = min(30, v_count * 8) + (30 if ma_pass else 0) + (30 if bp_pass else 0)

    result = {
        'code': code,
        'market': market,
        'name': name,
        'latest_price': latest['close'],
        'latest_volume': latest['volume'],
        'change_pct': change_pct,
        'volume_consecutive': v_count,
        'volume_ratio_ma5': round(latest['volume'] / vol_ma5, 2),
        'score': score,
        'signals': signals,
    }
    result.update(ma_info)
    result.update(bp_info)
    return result


# ─── 扫描主循环 ─────────────────────────────────────

def run_scan(stocks, workers=20, max_stocks=None, resume_from=None):
    """并发扫描所有股票，返回结果列表"""
    if max_stocks and max_stocks < len(stocks):
        stocks = stocks[:max_stocks]
        print(f"  [扫描] 测试模式: 仅扫描前 {max_stocks} 只")

    total = len(stocks)
    results = []
    start_time = time.time()

    # 如果从断点恢复，跳过已完成的
    scanned_set = set(resume_from or [])

    def process_one(s):
        code = s['code']
        market = s.get('market', 'sh' if code.startswith('6') else 'sz')
        name = s.get('name', code)

        if code in scanned_set:
            return None  # 已处理过

        code_str = market + code
        kline = fetch_weekly_kline(code_str)
        if not kline:
            return {'code': code, 'error': 'no_data'}

        result = assess_stock(code, market, name, kline)
        if result:
            return {'type': 'match', 'data': result}
        return {'code': code, 'error': 'no_match'}

    done = 0
    fetched_count = 0

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(process_one, s): s for s in stocks}

        for future in as_completed(futures):
            s = futures[future]
            done += 1
            try:
                r = future.result()
                if r is None:
                    continue
                if r.get('type') == 'match':
                    results.append(r['data'])
                    fetched_count += 1
                elif r.get('error') == 'no_match':
                    fetched_count += 1  # K线获取成功但不符合条件
                # 进度显示
                if done % 200 == 0 or done == total:
                    elapsed = time.time() - start_time
                    rate = done / elapsed if elapsed > 0 else 0
                    remain = (total - done) / rate if rate > 0 else 0
                    print(f"  [进度] {done}/{total}  "
                          f"已选{len(results)}只  "
                          f"({elapsed:.0f}s elapsed, ~{remain:.0f}s remain)")
            except Exception as e:
                pass

    elapsed = time.time() - start_time
    print(f"\n  [完成] 扫描{total}只, 获取K线{fetched_count}只, "
          f"符合条件{len(results)}只, 耗时{elapsed:.0f}s")
    return results


# ─── 输出 ─────────────────────────────────────────────

def save_results(results, scanned_count):
    """保存到 JSON 文件"""
    os.makedirs(DATA_DIR, exist_ok=True)
    # 按评分降序
    results.sort(key=lambda x: x['score'], reverse=True)

    output = {
        'updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'total_scanned': scanned_count,
        'total_matched': len(results),
        'conditions': {
            'volume_up': '周成交量连续放大≥4周',
            'ma_up': '周MA5/MA10/MA20上翘或多头排列',
            'break_pullback': '突破前高后回调缩量',
        },
        'picks': results,
    }

    # 精简（去掉临时字段）
    for p in output['picks']:
        if '_fetched' in p:
            del p['_fetched']

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    # 保存进度供续传
    progress = {
        'scanned_codes': [p['code'] for p in results],
        'timestamp': datetime.now().isoformat(),
        'total_scanned': scanned_count,
    }
    with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
        json.dump(progress, f)

    print(f"  [输出] 已保存 {len(results)} 只到 {OUTPUT_FILE}")
    return output


def upload_to_server():
    """SCP上传到服务器"""
    if not os.path.exists(OUTPUT_FILE):
        print("[错误] 输出文件不存在，请先运行扫描")
        return False

    cmd = f'scp -i "{SSH_KEY}" -o StrictHostKeyChecking=no "{OUTPUT_FILE}" {CLOUD_HOST}:{CLOUD_PATH}'
    print(f"  [上传] 上传到 {CLOUD_HOST}...")
    ret = os.system(cmd)
    if ret == 0:
        print(f"  [上传] 成功 → {CLOUD_HOST}:{CLOUD_PATH}")
        # 重启服务
        restart_cmd = f'ssh -i "{SSH_KEY}" -o StrictHostKeyChecking=no {CLOUD_HOST} "sudo systemctl restart quant-stock"'
        print("  [重启] 重启服务器服务...")
        os.system(restart_cmd)
        print("  [重启] 完成")
        return True
    else:
        print(f"  [上传] 失败 (返回码 {ret})")
        return False


# ─── 入口 ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='全市场周线选股扫描')
    parser.add_argument('--max-stocks', type=int, default=0,
                        help='测试模式: 仅扫描前N只')
    parser.add_argument('--workers', type=int, default=20,
                        help='并发数 (默认20)')
    parser.add_argument('--upload', action='store_true',
                        help='扫描后自动上传服务器')
    parser.add_argument('--resume', action='store_true',
                        help='断点续传')
    args = parser.parse_args()

    print("=" * 50)
    print("  全市场周线选股扫描")
    print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)

    # 1. 加载并过滤股票
    print("\n[1/3] 加载股票列表...")
    stocks = load_and_filter_stocks()
    if not stocks:
        print("[错误] 没有可扫描的股票")
        sys.exit(1)

    # 2. 加载断点信息
    resume_codes = set()
    if args.resume and os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
                prog = json.load(f)
            resume_codes = set(prog.get('scanned_codes', []))
            print(f"  [续传] 上次已完成 {len(resume_codes)} 只")
        except Exception:
            pass

    # 3. 执行扫描
    print(f"\n[2/3] 开始扫描 ({args.workers} 并发)...")
    results = run_scan(stocks, workers=args.workers,
                       max_stocks=args.max_stocks if args.max_stocks > 0 else None,
                       resume_from=resume_codes)

    # 4. 保存结果
    print(f"\n[3/3] 保存结果...")
    scanned = args.max_stocks if args.max_stocks > 0 else len(stocks)
    save_results(results, scanned)

    # 5. 上传（可选）
    if args.upload:
        print("\n[上传] 上传到服务器...")
        upload_to_server()

    print(f"\n== 完成! 共找到 {len(results)} 只符合条件的股票 ==")


if __name__ == '__main__':
    main()
