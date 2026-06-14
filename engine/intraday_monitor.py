"""盘中监控引擎 — 每5分钟扫描候选池，检测异动

数据流:
    candidates.json → 腾讯批量报价 → 异动检测 → 输出异动列表

不依赖 K线数据，只使用实时报价。
"""

import json
import os
import time
import threading
from datetime import datetime, date

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')
CANDIDATES_FILE = os.path.join(DATA_DIR, 'candidates.json')

# 异动标记
SURGE_VOLUME = '放量'      # 涨跌幅 > 4%
SURGE_PRICE = '异动'       # 涨跌幅 > 3%
SURGE_ACTIVE = '活跃'      # 换手率 > 5%
SURGE_HIGH = '冲高'        # 价格接近今日高点


class IntradayMonitor:
    """盘中监控器，每5分钟轮询候选池。"""

    def __init__(self):
        self._candidates = []       # [{code, market, name, ...}]
        self._alerts = []           # 当前异动列表
        self._alert_history = []    # 历史异动记录
        self._last_scan_time = None
        self._lock = threading.Lock()
        self._running = False
        self._latest_quotes = {}

        self.load_candidates()

    # ─── 候选池加载 ──────────────────────────────────

    def load_candidates(self):
        """从 candidates.json 加载候选池。"""
        if not os.path.exists(CANDIDATES_FILE):
            print(f"  [Monitor] 找不到 {CANDIDATES_FILE}，无候选池")
            self._candidates = []
            return False
        try:
            with open(CANDIDATES_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self._candidates = data.get('candidates', [])
            print(f"  [Monitor] 已加载 {len(self._candidates)} 只候选股")
            return True
        except Exception as e:
            print(f"  [Monitor] 加载失败: {e}")
            self._candidates = []
            return False

    def get_candidates(self):
        # 缓存为空时临时拉一次（非交易时段显示收盘价）
        if not self._latest_quotes and self._candidates:
            cs = self._build_codes_str()
            if cs:
                qs = self._fetch_quotes(cs)
                if qs:
                    self._latest_quotes = qs
        candidates = []
        for s in self._candidates:
            c2 = dict(s)
            q = self._latest_quotes.get(s["code"], {})
            c2["price"] = q.get("price", 0)
            c2["change_pct"] = q.get("change_pct", 0)
            candidates.append(c2)
        return candidates

    def get_candidate_count(self):
        return len(self._candidates)

    # ─── 核心扫描 ────────────────────────────────────

    def scan(self):
        """执行一次扫描：拉报价 → 检测异动 → 更新列表。"""
        if not self._candidates:
            return []

        codes_str = self._build_codes_str()
        if not codes_str:
            return []

        # 批量拉实时报价
        quotes = self._fetch_quotes(codes_str)
        if not quotes:
            return []

        # 检测异动
        alerts = self._detect_alerts(quotes)
        self._latest_quotes = quotes

        with self._lock:
            self._alerts = alerts
            self._last_scan_time = datetime.now()
            if alerts:
                self._alert_history.append({
                    'time': self._last_scan_time.strftime('%H:%M:%S'),
                    'count': len(alerts),
                    'stocks': [a['code'] for a in alerts],
                })
                # 保留最近20条历史
                if len(self._alert_history) > 20:
                    self._alert_history = self._alert_history[-20:]

        return alerts

    def _build_codes_str(self):
        """构建腾讯批量查询字符串：sh600519,sz000001。"""
        codes = []
        for s in self._candidates:
            m = 'sh' if s.get('market') == 'sh' else 'sz'
            codes.append(f"{m}{s['code']}")
        if not codes:
            return ''
        return ','.join(codes)

    def _fetch_quotes(self, codes_str):
        """拉腾讯批量实时报价。"""
        url = f'https://qt.gtimg.cn/q={codes_str}'
        try:
            import requests
            r = requests.get(url, timeout=10,
                             headers={'User-Agent': 'Mozilla/5.0'})
            if r.status_code != 200:
                return None
            return self._parse_tencent_response(r.text)
        except Exception as e:
            print(f"  [Monitor] 报价获取失败: {e}")
            return None

    @staticmethod
    def _parse_tencent_response(text):
        """解析腾讯批量报价返回。"""
        quotes = {}
        for line in text.strip().split('\n'):
            line = line.strip()
            if not line or not line.startswith('v_'):
                continue
            try:
                # 格式: v_marketcode="...~name~code~price~...~changePercent~...~turnover~...~high~low~..."
                parts = line.split('~')
                if len(parts) < 40:
                    continue
                market_code = parts[0].split('"')[0] if '"' in parts[0] else parts[0]
                market = 'sh' if market_code.startswith('v_1') else 'sz'
                name = parts[1]
                code = parts[2]
                price = float(parts[3]) if parts[3] else 0
                yesterday_close = float(parts[4]) if parts[4] else 0
                change_pct = float(parts[32]) if parts[32] else 0
                volume = int(parts[6]) if parts[6] else 0  # 手
                amount = float(parts[37]) if parts[37] else 0  # 万
                high = float(parts[33]) if parts[33] else 0
                low = float(parts[34]) if parts[34] else 0
                open_p = float(parts[5]) if parts[5] else 0
                turnover = float(parts[38]) if parts[38] else 0  # 换手率%
                pe = float(parts[39]) if parts[39] else 0
                quotes[code] = {
                    'code': code, 'market': market, 'name': name,
                    'price': price, 'yesterday_close': yesterday_close,
                    'change_pct': round(change_pct, 2),
                    'volume': volume, 'amount': amount,
                    'high': high, 'low': low, 'open': open_p,
                    'turnover': turnover, 'pe': pe,
                }
            except (ValueError, IndexError):
                continue
        return quotes

    def _detect_alerts(self, quotes):
        """对每只候选股检测异动，返回异动列表。"""
        alerts = []
        now = datetime.now()

        for s in self._candidates:
            code = s['code']
            q = quotes.get(code)
            if not q:
                continue

            sigs = []
            reasons = []

            # 1. 涨跌幅异动
            cp = q.get('change_pct', 0)
            if cp > 4:
                sigs.append(SURGE_VOLUME)
                reasons.append(f"大涨{cp:.1f}%")
            elif cp > 3:
                sigs.append(SURGE_PRICE)
                reasons.append(f"涨{cp:.1f}%")
            elif cp < -3:
                sigs.append(SURGE_PRICE)
                reasons.append(f"跌{cp:.1f}%")

            # 2. 换手率活跃
            tr = q.get('turnover', 0)
            if tr > 10:
                sigs.append(SURGE_ACTIVE)
                reasons.append(f"换手{tr:.1f}%")
            elif tr > 5:
                sigs.append(SURGE_ACTIVE)
                reasons.append(f"换手{tr:.1f}%")

            # 3. 冲高（价格接近今日高点）
            high = q.get('high', 0)
            low = q.get('low', 0)
            price = q.get('price', 0)
            if high > low and price > 0:
                high_pct = (price - low) / (high - low) * 100 if (high - low) > 0 else 0
                if high_pct > 95:
                    sigs.append(SURGE_HIGH)
                    reasons.append("接近日内高点")

            # 4. 成交额异动
            amt = q.get('amount', 0)
            if amt > 50000:  # 5亿以上
                reasons.append(f"成交额{amt/10000:.1f}亿")

            if len(sigs) >= 1 or (amt > 50000 and cp > 0):
                alerts.append({
                    'code': code,
                    'market': s.get('market', ''),
                    'name': q.get('name', s.get('name', '')),
                    'price': price,
                    'change_pct': cp,
                    'turnover': tr,
                    'amount': amt,
                    'high': high,
                    'low': low,
                    'sigs': sigs,
                    'reasons': reasons,
                    'time': now.strftime('%H:%M:%S'),
                })

        # 按异动强度排序
        def alert_score(a):
            score = 0
            if SURGE_VOLUME in a['sigs']: score += 30
            if SURGE_PRICE in a['sigs']: score += 20
            if SURGE_ACTIVE in a['sigs']: score += 15
            if SURGE_HIGH in a['sigs']: score += 10
            score += abs(a['change_pct']) * 2
            return -score

        alerts.sort(key=alert_score)
        return alerts

    # ─── 对外接口 ────────────────────────────────────

    def get_alerts(self):
        """获取当前异动列表。"""
        with self._lock:
            return list(self._alerts)

    def get_history(self):
        """获取历史异动记录。"""
        with self._lock:
            return list(self._alert_history)

    def get_status(self):
        """获取监控状态。"""
        with self._lock:
            return {
                'candidate_count': len(self._candidates),
                'alert_count': len(self._alerts),
                'last_scan': self._last_scan_time.strftime('%H:%M:%S') if self._last_scan_time else None,
                'market_open': self._is_market_open(),
            }

    @staticmethod
    def _is_market_open():
        """简单判断是否在交易时段。"""
        now = datetime.now()
        # 周末
        if now.weekday() >= 5:
            return False
        h, m = now.hour, now.minute
        tm = h * 60 + m
        # 上午 9:30-11:30, 下午 13:00-15:00
        return (570 <= tm <= 690) or (780 <= tm <= 900)

    def is_trading_time(self):
        return self._is_market_open()


# ─── 模块级单例 ──────────────────────────────────────

_global_monitor = None
_monitor_lock = threading.Lock()
_monitor_thread = None


def get_monitor():
    """获取全局 IntradayMonitor 单例。"""
    global _global_monitor
    if _global_monitor is None:
        with _monitor_lock:
            if _global_monitor is None:
                _global_monitor = IntradayMonitor()
    return _global_monitor


def start_monitor_loop(interval=300):
    """在后台线程启动定时扫描。

    interval: 扫描间隔，默认300秒(5分钟)
    """
    global _monitor_thread
    if _monitor_thread and _monitor_thread.is_alive():
        return

    monitor = get_monitor()

    def loop():
        while True:
            try:
                if monitor.is_trading_time():
                    monitor.scan()
                time.sleep(interval)
            except Exception as e:
                print(f"  [Monitor] 扫描异常: {e}")
                time.sleep(interval)

    _monitor_thread = threading.Thread(target=loop, daemon=True)
    _monitor_thread.start()
    print(f"  [Monitor] 后台监控已启动，间隔 {interval//60} 分钟")
