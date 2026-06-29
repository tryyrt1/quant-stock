"""
主升浪前兆检测 + 起爆时间预测引擎
===================================
基于252只历史主升浪股票的前20日量价规律分析。

用法:
    from engine.surge_predictor import SurgePredictor
    sp = SurgePredictor()
    results = sp.scan(['000001', '000002', ...])  # 传入股票代码列表
"""

import json, os, math, time, requests
from datetime import datetime
from collections import defaultdict

# ===== 形态定义（基于252只历史数据分析结果）=====

PATTERNS = {
    'D-缩量整理型': {
        'desc': '横盘+极度缩量，洗盘尾声，爆发前夜',
        'ref': {'gain_range': (-5, 5), 'vol_ratio': 0.59, 'up_ratio': 0.53, 'amp': 5.0,
                'consec_up_min': 2, 'price_trend': '横盘'},
        'trigger': '放量突破前高',
        'est_explosion_days': (1, 3),
        'score_weight': 0.15,
        'emoji': '🔥',
    },
    'E-碎步小阳型': {
        'desc': '横盘但小阳线居多，隐蔽建仓',
        'ref': {'gain_range': (-5, 5), 'vol_ratio': 1.15, 'up_ratio': 0.62, 'amp': 4.8,
                'consec_up_min': 4, 'price_trend': '小阳推升'},
        'trigger': '量比>1.5 + 加速阳线',
        'est_explosion_days': (5, 10),
        'score_weight': 0.12,
        'emoji': '🌱',
    },
    'C-放量异动型': {
        'desc': '横盘+放量+高振幅，主力试盘',
        'ref': {'gain_range': (-5, 5), 'vol_ratio': 1.40, 'up_ratio': 0.60, 'amp': 6.0,
                'consec_up_min': 3, 'price_trend': '放量异动'},
        'trigger': '缩量回踩后放量突破',
        'est_explosion_days': (1, 2),
        'score_weight': 0.08,
        'emoji': '💥',
    },
    'I-深蹲起跳型': {
        'desc': '前20日大跌>15%，超跌反弹',
        'ref': {'gain_range': (-100, -15), 'vol_ratio': 0.77, 'up_ratio': 0.39, 'amp': 5.1,
                'consec_up_min': 2, 'price_trend': '急跌'},
        'trigger': '首次放量阳线止跌',
        'est_explosion_days': (3, 7),
        'score_weight': 0.12,
        'emoji': '🏋️',
    },
    'B-温和上涨型': {
        'desc': '前20日涨5-15%，缓慢吸筹',
        'ref': {'gain_range': (5, 15), 'vol_ratio': 1.17, 'up_ratio': 0.57, 'amp': 4.7,
                'consec_up_min': 3, 'price_trend': '缓涨'},
        'trigger': '加速放量',
        'est_explosion_days': (7, 14),
        'score_weight': 0.20,
        'emoji': '📈',
    },
    'H-缩量阴跌型': {
        'desc': '前20日缩量阴跌洗盘',
        'ref': {'gain_range': (-15, -5), 'vol_ratio': 0.81, 'up_ratio': 0.46, 'amp': 4.6,
                'consec_up_min': 2, 'price_trend': '阴跌'},
        'trigger': '放量阳线反转',
        'est_explosion_days': (3, 7),
        'score_weight': 0.18,
        'emoji': '📉',
    },
    'A-加速拉升型': {
        'desc': '前20日已大涨>15%，追高风险大',
        'ref': {'gain_range': (15, 100), 'vol_ratio': 1.79, 'up_ratio': 0.62, 'amp': 6.1,
                'consec_up_min': 4, 'price_trend': '加速'},
        'trigger': '高位放量滞涨=见顶信号',
        'est_explosion_days': (0, 0),
        'score_weight': 0.05,
        'emoji': '🚀',
    },
    'F-无序震荡型': {
        'desc': '前20日横盘无方向，等待突破',
        'ref': {'gain_range': (-5, 5), 'vol_ratio': 1.10, 'up_ratio': 0.49, 'amp': 4.3,
                'consec_up_min': 2, 'price_trend': '震荡'},
        'trigger': '放量突破箱体',
        'est_explosion_days': (None, None),
        'score_weight': 0.05,
        'emoji': '🔀',
    },
}

# 优先关注形态（接近起爆）
WATCH_PRIORITY = ['D-缩量整理型', 'C-放量异动型', 'E-碎步小阳型', 'I-深蹲起跳型']


class SurgePredictor:
    """主升浪前兆检测器"""

    def __init__(self, cache_dir=None):
        self.cache_dir = cache_dir or os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')
        self._kline_cache = {}
        self._quote_cache = {}
        self._session = requests.Session()
        self._session.headers.update({'User-Agent': 'Mozilla/5.0'})

    # ─── 数据获取 ─────────────────────────────────

    def fetch_kline(self, code_str, days=25):
        """获取K线（复用腾讯API），带内存缓存"""
        cache_key = f"{code_str}_{days}"
        if cache_key in self._kline_cache:
            return self._kline_cache[cache_key]

        url = f'https://ifzq.gtimg.cn/appstock/app/fqkline/get?param={code_str},day,,,{days},qfq'
        try:
            r = self._session.get(url, timeout=5)
            if r.status_code != 200:
                return []
            raw = r.json()
            data = raw.get('data', {})
            klines = (data.get(code_str, {}).get('qfqday')
                      or data.get(code_str, {}).get('day')
                      or [])
            result = []
            for k in klines:
                try:
                    result.append({
                        'date': str(k[0]),
                        'open': float(k[1]),
                        'close': float(k[2]),
                        'high': float(k[3]),
                        'low': float(k[4]),
                        'volume': int(float(k[5])),
                    })
                except:
                    pass
            # 按日期排序，取最后20个交易日
            result.sort(key=lambda x: x['date'])
            result = result[-25:]  # 多取几个防止缺失
            self._kline_cache[cache_key] = result
            return result
        except:
            return []

    def fetch_quote(self, code_str):
        """获取腾讯实时行情"""
        if code_str in self._quote_cache:
            return self._quote_cache[code_str]
        url = f'https://qt.gtimg.cn/q={code_str}'
        try:
            r = self._session.get(url, timeout=5)
            r.encoding = 'gbk'
            for line in r.text.split('\n'):
                m = __import__('re').search(r'v_[a-z]+\d+="(.+)"', line)
                if not m:
                    continue
                f = m.group(1).split('~')
                if len(f) < 40:
                    continue
                result = {
                    'code': f[2], 'name': f[1],
                    'price': self._to_f(f[3]),
                    'change_pct': self._to_f(f[32]),
                    'turnover': self._to_f(f[38]),
                    'vol_ratio': self._to_f(f[37]),
                    'volume': self._to_i(f[6]),
                }
                self._quote_cache[code_str] = result
                return result
        except:
            pass
        return {}

    @staticmethod
    def _to_f(v):
        try:
            return float(v)
        except:
            return 0.0

    @staticmethod
    def _to_i(v):
        try:
            return int(float(v))
        except:
            return 0

    # ─── 指标计算 ─────────────────────────────────

    def compute_metrics(self, klines):
        """从K线数据计算前20日量价指标"""
        if len(klines) < 10:
            return None

        # 取最近20条
        data = klines[-20:] if len(klines) >= 20 else klines
        n = len(data)

        closes = [d['close'] for d in data]
        opens = [d['open'] for d in data]
        highs = [d['high'] for d in data]
        lows = [d['low'] for d in data]
        vols = [d['volume'] for d in data]

        # 涨跌幅
        gain_pct = (closes[-1] - closes[0]) / closes[0] * 100 if closes[0] > 0 else 0

        # 日均振幅
        amps = [(highs[i] - lows[i]) / (lows[i] or 1) * 100 for i in range(n)]
        avg_amp = sum(amps) / n

        # 阳线比例
        up_days = sum(1 for i in range(n) if closes[i] >= opens[i])
        up_ratio = up_days / n

        # 每日涨跌幅
        daily_gains = []
        for i in range(1, n):
            if closes[i-1] > 0:
                daily_gains.append((closes[i] - closes[i-1]) / closes[i-1] * 100)

        # 量比趋势：后10日 / 前10日
        if n >= 20:
            vol_first = sum(vols[:10]) / 10
            vol_second = sum(vols[10:]) / 10
            vol_trend = vol_second / vol_first if vol_first > 0 else 1.0
        elif n >= 10:
            half = n // 2
            vol_first = sum(vols[:half]) / half
            vol_second = sum(vols[half:]) / (n - half)
            vol_trend = vol_second / vol_first if vol_first > 0 else 1.0
        else:
            vol_trend = 1.0

        # 近3日量比（当日量/20日均量）
        recent_vol_ratio = None
        avg_vol = sum(vols) / n
        if avg_vol > 0:
            recent_vol_ratio = vols[-1] / avg_vol

        # 近3日/前段振幅比
        amp_ratio = None
        if n >= 8:
            recent_amp = sum(amps[-3:]) / 3
            early_amp = sum(amps[:-3]) / max(1, n - 3)
            amp_ratio = recent_amp / early_amp if early_amp > 0 else 1.0

        # 最大连阳/连阴
        max_consec_up = max_consec_down = cur_up = cur_down = 0
        for g in daily_gains:
            if g > 0:
                cur_up += 1
                cur_down = 0
                max_consec_up = max(max_consec_up, cur_up)
            else:
                cur_down += 1
                cur_up = 0
                max_consec_down = max(max_consec_down, cur_down)

        return {
            'gain_pct': round(gain_pct, 2),
            'avg_amp': round(avg_amp, 2),
            'up_ratio': round(up_ratio, 2),
            'vol_trend': round(vol_trend, 2),
            'recent_vol_ratio': round(recent_vol_ratio, 2) if recent_vol_ratio else None,
            'amp_ratio': round(amp_ratio, 2) if amp_ratio else None,
            'consec_up': max_consec_up,
            'consec_down': max_consec_down,
            'avg_vol': int(avg_vol),
            'last_vol': vols[-1],
            'last_close': closes[-1],
            'last_open': opens[-1],
            'n_days': n,
        }

    # ─── 形态分类 ─────────────────────────────────

    def classify(self, metrics):
        """基于指标匹配最接近的形态"""
        if not metrics:
            return '未知', 0

        scores = {}
        for pname, pdef in PATTERNS.items():
            ref = pdef['ref']
            score = 0

            # 涨跌幅匹配
            g = metrics['gain_pct']
            g_low, g_high = ref['gain_range']
            if g_low <= g <= g_high:
                score += 30
            else:
                dist = min(abs(g - g_low), abs(g - g_high))
                score += max(0, 30 - dist * 2)

            # 量比匹配
            if metrics['vol_trend']:
                vol_diff = abs(metrics['vol_trend'] - ref['vol_ratio'])
                score += max(0, 25 - vol_diff * 20)

            # 阳线比例匹配
            if metrics['up_ratio']:
                up_diff = abs(metrics['up_ratio'] - ref['up_ratio'])
                score += max(0, 20 - up_diff * 50)

            # 振幅匹配
            amp_diff = abs(metrics['avg_amp'] - ref['amp'])
            score += max(0, 15 - amp_diff * 3)

            # 连阳匹配
            consec_diff = abs(metrics['consec_up'] - ref['consec_up_min'])
            score += max(0, 10 - consec_diff * 3)

            scores[pname] = round(score, 1)

        if not scores:
            return '未知', 0

        best = max(scores, key=scores.get)
        return best, scores[best]

    # ─── 准备度评分 ─────────────────────────────────

    def score_readiness(self, metrics, pattern_name):
        """计算起爆准备度 0-100"""
        if not metrics or pattern_name == '未知':
            return 0, '数据不足'

        reasons = []

        # 1. 洗盘充分度 (40分)
        wash_score = 0
        if metrics['vol_trend'] and metrics['vol_trend'] < 0.8:
            wash_score += 20
            reasons.append('极度缩量')
        elif metrics['vol_trend'] and metrics['vol_trend'] < 1.0:
            wash_score += 10
            reasons.append('缩量整理')

        if metrics['amp_ratio'] and metrics['amp_ratio'] < 0.8:
            wash_score += 10
            reasons.append('振幅收缩')
        elif metrics['amp_ratio'] and metrics['amp_ratio'] < 1.0:
            wash_score += 5

        if metrics['consec_down'] >= 3:
            wash_score += 10
            reasons.append(f'连阴{metrics["consec_down"]}天洗盘')

        # 2. 触发信号强度 (40分)
        trigger_score = 0
        if metrics['recent_vol_ratio'] and metrics['recent_vol_ratio'] > 2.0:
            trigger_score += 20
            reasons.append('放量突破')
        elif metrics['recent_vol_ratio'] and metrics['recent_vol_ratio'] > 1.5:
            trigger_score += 10
            reasons.append('温和放量')

        if metrics['amp_ratio'] and metrics['amp_ratio'] > 1.3:
            trigger_score += 10
            reasons.append('振幅扩张')

        is_up_day = metrics['last_close'] >= metrics['last_open']
        if is_up_day:
            trigger_score += 10
            reasons.append('当日阳线')

        # 3. 形态匹配度 (20分)
        _, match_score = self.classify(metrics)
        pattern_score = min(20, match_score / 5)

        total = min(100, wash_score + trigger_score + pattern_score)

        return total, ' + '.join(reasons) if reasons else '待观察'

    # ─── 起爆时间预测 ─────────────────────────────

    def predict_timing(self, metrics, pattern_name):
        """预测预计起爆时间"""
        pdef = PATTERNS.get(pattern_name)
        if not pdef:
            return '待观察', 'orange'

        low, high = pdef['est_explosion_days']

        # 特殊判断
        if pattern_name == 'D-缩量整理型':
            # 量比越低越接近起爆
            if metrics['vol_trend'] and metrics['vol_trend'] < 0.6:
                return '🔥 1-2天', 'red'
            return '1-3天', 'orange'

        elif pattern_name == 'C-放量异动型':
            if metrics['recent_vol_ratio'] and metrics['recent_vol_ratio'] > 2.0:
                return '🔥 随时爆发', 'red'
            return '1-2天', 'red'

        elif pattern_name == 'E-碎步小阳型':
            if metrics['consec_up'] >= 8:
                return '🔥 1-3天', 'orange'
            return f'{low}-{high}天', 'yellow'

        elif pattern_name == 'I-深蹲起跳型':
            if metrics['recent_vol_ratio'] and metrics['recent_vol_ratio'] > 1.5:
                return '🔥 1-3天', 'red'
            return f'{low}-{high}天', 'orange'

        elif pattern_name == 'B-温和上涨型':
            return f'{low}-{high}天', 'yellow'

        elif pattern_name in ('H-缩量阴跌型',):
            if metrics['recent_vol_ratio'] and metrics['recent_vol_ratio'] > 1.5:
                return '🔥 1-3天', 'red'
            return f'{low}-{high}天', 'orange'

        elif pattern_name == 'A-加速拉升型':
            return '已拉升中', 'yellow'

        else:
            return '待观察', 'grey'

    # ─── 批量扫描 ─────────────────────────────────

    def scan(self, stock_codes, stock_names=None, market_map=None, max_results=50):
        """批量扫描股票，返回按准备度排序的结果

        stock_codes: ['000001', '000002', ...]
        stock_names: {code: name} 可选
        market_map: {code: 'sh'|'sz'} 可选，默认根据代码推断
        max_results: 最多返回N只
        """
        if stock_names is None:
            stock_names = {}
        if market_map is None:
            market_map = {}

        results = []
        total = len(stock_codes)

        for i, code in enumerate(stock_codes):
            # 判断市场
            market = market_map.get(code, 'sh' if code.startswith('6') else 'sz')
            full_code = market + code

            # 获取K线
            klines = self.fetch_kline(full_code)
            if not klines or len(klines) < 10:
                continue

            # 计算指标
            metrics = self.compute_metrics(klines)
            if not metrics:
                continue

            # 分类
            pattern, match_score = self.classify(metrics)

            # 获取实时行情
            quote = self.fetch_quote(full_code)
            price = quote.get('price', metrics['last_close'])
            name = stock_names.get(code, quote.get('name', ''))
            change_pct = quote.get('change_pct', 0)

            # 准备度评分
            readiness, reason = self.score_readiness(metrics, pattern)

            # 起爆预测
            timing, urgency = self.predict_timing(metrics, pattern)

            # 综合排序分 (准备度 + 形态权重 + 急迫度加成)
            pdef = PATTERNS.get(pattern, {})
            weight = pdef.get('score_weight', 0.05)
            priority_bonus = 10 if pattern in WATCH_PRIORITY else 0
            urgency_bonus = 15 if urgency == 'red' else 5 if urgency == 'orange' else 0
            sort_score = readiness + priority_bonus + urgency_bonus

            results.append({
                'code': code,
                'name': name,
                'price': round(price, 2),
                'change_pct': round(change_pct, 2),
                'pattern': pattern,
                'match_score': match_score,
                'readiness': readiness,
                'reason': reason,
                'timing': timing,
                'urgency': urgency,
                'sort_score': sort_score,
                'metrics': {
                    'gain_pct': metrics['gain_pct'],
                    'avg_amp': metrics['avg_amp'],
                    'up_ratio': metrics['up_ratio'],
                    'vol_trend': metrics['vol_trend'],
                    'recent_vol_ratio': metrics['recent_vol_ratio'],
                    'consec_up': metrics['consec_up'],
                    'consec_down': metrics['consec_down'],
                },
                'pdesc': pdef.get('desc', ''),
                'emoji': pdef.get('emoji', ''),
            })

            if (i + 1) % 100 == 0:
                print(f"  [SurgePredictor] {i+1}/{total}", flush=True)
            time.sleep(0.05)  # 防止被腾讯封

        # 排序：准备度降序，优先关注形态加分
        results.sort(key=lambda x: -x['sort_score'])
        return results[:max_results]

    def clear_cache(self):
        """清理内存缓存"""
        self._kline_cache.clear()
        self._quote_cache.clear()
