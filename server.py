"""AI 量化选股系统 - 主服务器"""
import json, os, socket, re, time, threading
from flask import Flask, jsonify, request, Response, send_from_directory

from engine.indicators import *
from engine.factors import analyze_factors
from engine.news import fetch_news, analyze_sentiment
from engine.patterns import scan_patterns

app = Flask(__name__, static_folder='static')
DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
WATCHLIST_FILE = os.path.join(DATA_DIR, 'watchlist.json')
REALTIME_CACHE = {}  # {code: {data, time}}

# 确保数据目录和自选股文件存在 (gunicorn 下也会执行)
os.makedirs(DATA_DIR, exist_ok=True)
if not os.path.exists(WATCHLIST_FILE):
    with open(WATCHLIST_FILE, 'w', encoding='utf-8') as f:
        json.dump([], f)

# =================== 工具函数 ===================

def load_watchlist():
    try:
        with open(WATCHLIST_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return []

def save_watchlist(wl):
    with open(WATCHLIST_FILE, 'w', encoding='utf-8') as f:
        json.dump(wl, f, ensure_ascii=False, indent=2)

def fetch_tencent_quote(codes_str):
    """获取腾讯实时行情"""
    url = f'https://qt.gtimg.cn/q={codes_str}'
    import requests
    r = requests.get(url, timeout=8, headers={'User-Agent': 'Mozilla/5.0'})
    r.encoding = 'gbk'
    results = []
    for line in r.text.split('\n'):
        m = re.search(r'v_[a-z]+\d+="(.+)"', line)
        if not m: continue
        f = m.group(1).split('~')
        if len(f) < 40: continue
        results.append({
            'code': f[2], 'name': f[1],
            'price': _f(f[3]), 'yesterdayClose': _f(f[4]),
            'open': _f(f[5]), 'volume': _int(f[6]),
            'high': _f(f[33]), 'low': _f(f[34]),
            'change': _f(f[31]), 'changePercent': _f(f[32]),
            'turnover': _f(f[38]), 'pe': _f(f[39]),
            'pb': _f(f[46]),
        })
    return {r['code']: r for r in results}

def fetch_kline(code_str, days=120):
    """获取K线数据"""
    url = f'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={code_str},day,,,{days},qfq'
    import requests
    r = requests.get(url, timeout=8, headers={'User-Agent': 'Mozilla/5.0'})
    raw = r.json()
    data = raw.get('data', {})
    klines = data.get(code_str, {}).get('qfqday') or data.get(code_str, {}).get('day') or []
    return [{'date': k[0], 'open': _f(k[1]), 'close': _f(k[2]),
             'high': _f(k[3]), 'low': _f(k[4]), 'volume': _int(k[5])} for k in klines]

def _f(v):
    try: return float(v)
    except: return 0.0
def _int(v):
    try: return int(v)
    except: return 0

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        return s.getsockname()[0]
    except:
        return '127.0.0.1'
    finally:
        s.close()

# =================== API 路由 ===================

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

@app.route('/api/watchlist', methods=['GET', 'POST', 'DELETE'])
def watchlist_api():
    wl = load_watchlist()

    if request.method == 'GET':
        return jsonify(wl)

    if request.method == 'POST':
        item = request.json
        # 格式: {code, market, name} 或 {code: '600519', market: 'sh'}
        code = item.get('code', '')
        market = item.get('market', 'sh')
        name = item.get('name', code)

        if not code:
            return jsonify({'error': '缺少股票代码'}), 400

        exists = any(s['code'] == code and s['market'] == market for s in wl)
        if not exists:
            wl.append({'code': code, 'market': market, 'name': name, 'added': time.strftime('%Y-%m-%d')})
            save_watchlist(wl)

        return jsonify(wl)

    if request.method == 'DELETE':
        code = request.args.get('code', '')
        market = request.args.get('market', 'sh')
        wl = [s for s in wl if not (s['code'] == code and s['market'] == market)]
        save_watchlist(wl)
        return jsonify(wl)


@app.route('/api/quote')
def quote_api():
    codes_str = request.args.get('codes', '')
    if not codes_str:
        return jsonify({'error': 'missing codes'}), 400
    data = fetch_tencent_quote(codes_str)
    return jsonify(data)


@app.route('/api/kline')
def kline_api():
    code = request.args.get('code', '')
    days = int(request.args.get('days', 120))
    if not code:
        return jsonify({'error': 'missing code'}), 400
    data = fetch_kline(code, days)
    return jsonify(data)


@app.route('/api/stock/<code>')
def stock_detail(code):
    """股票综合分析"""
    market = request.args.get('market', 'sh')
    full_code = market + code

    # 并行获取数据
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as exe:
        f_quote = exe.submit(fetch_tencent_quote, full_code)
        f_kline = exe.submit(fetch_kline, full_code, 120)
        f_news = exe.submit(fetch_news, code, market)

    quotes = f_quote.result()
    kline = f_kline.result()
    news_raw = f_news.result()

    quote = quotes.get(code, {}) if quotes else {}

    # 情感分析
    sentiment_score, news_analyzed = analyze_sentiment(news_raw)

    # 压力位/支撑位 (先算，因子分析要用)
    from engine.indicators import calc_support_resistance
    sr = calc_support_resistance(kline) if len(kline) >= 20 else {}

    # 因子分析
    factors = analyze_factors(kline, quote, sentiment_score, sr) if len(kline) >= 60 else {'score': 50, 'advice': '数据不足'}

    # 技术指标概要
    closes = [k['close'] for k in kline]
    indicators = {}
    if len(closes) >= 60:
        rsi = calc_rsi(closes, 14)
        macd = calc_macd(closes)
        indicators = {
            'rsi': round(rsi[-1], 2) if rsi[-1] else None,
            'macd_dif': round(macd['dif'][-1], 3) if macd['dif'] else None,
            'macd_dea': round(macd['dea'][-1], 3) if macd['dea'] else None,
            'macd': round(macd['macd'][-1], 3) if macd['macd'] else None,
            'ma5': round(calc_ma(closes, 5)[-1], 2) if calc_ma(closes, 5)[-1] else None,
            'ma20': round(calc_ma(closes, 20)[-1], 2) if calc_ma(closes, 20)[-1] else None,
            'ma60': round(calc_ma(closes, 60)[-1], 2) if calc_ma(closes, 60)[-1] else None,
        }

    return jsonify({
        'code': code,
        'market': market,
        'quote': quote,
        'kline': kline[-60:],  # 最近60条
        'indicators': indicators,
        'factors': factors,
        'sr': sr,
        'news': news_analyzed[:10],
        'sentiment': round(sentiment_score, 2),
    })


@app.route('/api/scan')
def scan_watchlist():
    """扫描自选股，批量分析"""
    wl = load_watchlist()
    if not wl:
        return jsonify({'results': [], 'message': '自选股列表为空'})

    codes_str = ','.join([s['market'] + s['code'] for s in wl])
    quotes = fetch_tencent_quote(codes_str)

    results = []
    for s in wl:
        q = quotes.get(s['code'], {})
        # 简略分析 (详细分析点进去看)
        score = 50
        advice = '持有'
        pe = abs(q.get('pe', 0) or 0)
        if 0 < pe < 20: score += 10
        elif pe > 50: score -= 10
        if q.get('changePercent', 0) > 0: score += 5
        else: score -= 5
        score = max(0, min(100, score))
        if score >= 65: advice = '买入'
        elif score <= 35: advice = '卖出'
        else: advice = '持有'

        results.append({
            'code': s['code'],
            'market': s['market'],
            'name': q.get('name', s.get('name', s['code'])),
            'price': q.get('price', 0),
            'changePercent': q.get('changePercent', 0),
            'change': q.get('change', 0),
            'pe': q.get('pe', 0),
            'score': score,
            'advice': advice,
        })

    results.sort(key=lambda x: x['score'], reverse=True)
    return jsonify({'results': results, 'count': len(results)})


@app.route('/api/scan/patterns', methods=['POST'])
def scan_patterns_api():
    """扫描自选股，识别技术形态/选股模式"""
    wl = load_watchlist()
    if not wl:
        return jsonify({'patterns': [], 'message': '自选股列表为空'})

    import concurrent.futures

    def fetch_with_code(s):
        full = s['market'] + s['code']
        try:
            k = fetch_kline(full, 120)
            return s['code'], s['market'], s.get('name', s['code']), k
        except:
            return s['code'], s['market'], s.get('name', s['code']), []

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as exe:
        kline_results = list(exe.map(fetch_with_code, wl))

    # 构建 klines_all dict
    klines_all = {}
    code_info = {}
    for code, market, name, k in kline_results:
        if len(k) >= 60:
            klines_all[f'{market}{code}'] = k
            code_info[f'{market}{code}'] = {'code': code, 'market': market, 'name': name}

    raw = scan_patterns(klines_all)

    # 格式化输出
    patterns_out = []
    for full_code, matches in raw.items():
        info = code_info.get(full_code, {})
        for m in matches:
            patterns_out.append({
                'code': info.get('code', full_code),
                'market': info.get('market', 'sh'),
                'name': info.get('name', full_code),
                'pattern_key': m['key'],
                'pattern_name': m['name'],
                'label': m['info'].get('label', ''),
                'detail': {k: v for k, v in m['info'].items() if k != 'label'},
            })

    # 按模式名称分组
    return jsonify({
        'patterns': patterns_out,
        'count': len(patterns_out),
        'stocks_matched': len(raw),
    })


# 全市场股票列表缓存 (5分钟)
_STOCK_LIST_CACHE = {'time': 0, 'data': []}

def fetch_a_share_list():
    """从东方财富获取全A股列表，排除创业板/科创板/ST"""
    now = time.time()
    if now - _STOCK_LIST_CACHE['time'] < 300 and _STOCK_LIST_CACHE['data']:
        return _STOCK_LIST_CACHE['data']

    url = 'http://push2.eastmoney.com/api/qt/clist/get'
    params = {
        'pn': 1, 'pz': 10000, 'po': 1, 'np': 1,
        'fltt': 2, 'invt': 2, 'fid': 'f3',
        'fs': 'm:0+t:6,m:0+t:13,m:1+t:2,m:1+t:23',
        'fields': 'f12,f14,f2,f3,f5,f20'
    }
    import requests as req
    try:
        r = req.get(url, params=params, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
        data = r.json()
    except:
        return _STOCK_LIST_CACHE['data'] or []

    stocks = []
    for item in data.get('data', {}).get('diff', []):
        code = str(item.get('f12', ''))
        name = str(item.get('f14', ''))
        price = item.get('f2')
        if price is None: continue
        price = float(price)
        volume = item.get('f5', 0) or 0

        if code.startswith('3') or code.startswith('688'): continue
        if 'ST' in name.upper() or '*' in name.upper(): continue
        if price <= 0 or volume <= 0: continue
        if price < 2 or price > 200: continue

        change_pct = item.get('f3', 0) or 0
        market = 'sh' if code.startswith('6') else 'sz'
        stocks.append({'code': code, 'market': market, 'name': name,
                       'price': price, 'volume': volume, 'change_pct': change_pct})

    _STOCK_LIST_CACHE['time'] = now
    _STOCK_LIST_CACHE['data'] = stocks
    return stocks


@app.route('/api/scan/market', methods=['POST'])
def scan_market_api():
    """全市场形态扫描 - 排除创业板/科创板/ST"""
    stocks = fetch_a_share_list()
    if not stocks:
        return jsonify({'error': '获取股票列表失败', 'patterns': []}), 500

    total = len(stocks)
    # 按成交量排序，取前200只最活跃的，排除涨停/涨幅过大的
    stocks.sort(key=lambda x: abs(x.get('volume', 0)), reverse=True)
    candidates = [s for s in stocks[:300] if (s.get('change_pct', 0) or 0) < 7][:200]

    import concurrent.futures
    def fetch_kline_for_stock(s):
        try:
            k = fetch_kline(s['market'] + s['code'], 120)
            return s['code'], s['market'], s['name'], k
        except:
            return s['code'], s['market'], s['name'], []

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as exe:
        kline_results = list(exe.map(fetch_kline_for_stock, candidates))

    klines_all = {}
    code_info = {}
    for code, market, name, k in kline_results:
        if len(k) >= 60:
            klines_all[f'{market}{code}'] = k
            code_info[f'{market}{code}'] = {'code': code, 'market': market, 'name': name}

    candidate_lookup = {s['code']: s for s in candidates}

    raw = scan_patterns(klines_all)
    patterns_out = []
    for full_code, matches in raw.items():
        info = code_info.get(full_code, {})
        cand = candidate_lookup.get(info.get('code', ''), {})
        chg = cand.get('change_pct', 0) or 0
        risk = ''
        if chg >= 9.5: risk = '涨停'
        elif chg >= 7: risk = '涨幅过大'
        for m in matches:
            patterns_out.append({
                'code': info.get('code', full_code),
                'market': info.get('market', 'sh'),
                'name': info.get('name', full_code),
                'pattern_key': m['key'],
                'pattern_name': m['name'],
                'label': m['info'].get('label', ''),
                'risk': risk,
                'change_pct': round(chg, 2),
                'detail': {k: v for k, v in m['info'].items() if k != 'label'},
            })

    return jsonify({
        'patterns': patterns_out,
        'count': len(patterns_out),
        'stocks_matched': len(raw),
        'total_scanned': total,
        'candidates': len(candidates),
    })


# =================== 启动 ===================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    ip = get_local_ip()
    print(f'=== AI 量化选股系统 ===')
    print(f'   本地: http://127.0.0.1:{port}')
    if ip != '127.0.0.1':
        print(f'   局域网: http://{ip}:{port}')
    print(f'   自选股文件: {WATCHLIST_FILE}')
    print(f'   Ctrl+C 停止')
    print(f'   部署模式: {"云服务器" if os.environ.get("PORT") else "本地开发"}')
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
