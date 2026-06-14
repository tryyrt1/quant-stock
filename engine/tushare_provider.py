"""Tushare Pro 统一数据层 — 限速 + 缓存 + 降级

用法:
    from engine.tushare_provider import get_provider
    tp = get_provider()
    if tp.available:
        df = tp.daily_basic()          # 全市场PE/PB/市值
        data = tp.fina_indicator(code)  # 单只股票基本面
"""

import os
import time
import threading
from datetime import datetime, date

import pandas as pd

# ─── Token ──────────────────────────────────────────────
TOKEN = os.environ.get('TUSHARE_TOKEN', '')

# ─── 令牌桶限速器 ──────────────────────────────────────

class TokenBucket:
    """令牌桶：确保每秒不超过 N 次调用。"""

    def __init__(self, rate_per_minute=200, initial_burst=30):
        self.rate = rate_per_minute / 60.0  # 每秒允许的调用数
        self.capacity = rate_per_minute     # 最大令牌上限
        self.tokens = initial_burst         # 初始暴发限制，避免滚动窗口超限
        self.last_time = time.time()
        self._lock = threading.Lock()
        self._last_error_time = 0

    def consume(self):
        """等待直到有可用令牌。"""
        with self._lock:
            now = time.time()
            elapsed = now - self.last_time
            self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
            self.last_time = now

            if self.tokens >= 1:
                self.tokens -= 1
                return True

            # 令牌不够，等待
            wait = (1 - self.tokens) / self.rate
        time.sleep(wait)
        return self.consume()  # 递归重试


# ─── Tushare 提供器 ──────────────────────────────────

class TushareProvider:
    """统一 Tushare 数据接口。"""

    def __init__(self, token=TOKEN):
        self._token = token
        self._pro = None
        self._bucket = TokenBucket(rate_per_minute=200)
        self._lock = threading.Lock()

        # 缓存
        self._daily_basic_cache = {'data': None, 'date': None}
        self._fina_cache = {}        # code -> {date_str: dict}
        self._fina_cache_lock = threading.Lock()

        self._available = False
        self._init()

    def _init(self):
        if not self._token:
            print("  [Tushare] TUSHARE_TOKEN 未设置，不可用")
            return
        try:
            import tushare as ts
            ts.set_token(self._token)
            self._pro = ts.pro_api()
            # 测试连通性
            df = self._pro.daily_basic(trade_date=self._last_trade_day(),
                                       fields='ts_code', limit=1)
            self._available = len(df) > 0
            if self._available:
                print(f"  [Tushare] 已连接 (Token: {self._token[:8]}...)")
        except Exception as e:
            print(f"  [Tushare] 初始化失败: {e}")
            self._available = False

    @property
    def available(self):
        return self._available

    @staticmethod
    def _last_trade_day():
        """返回最近交易日 YYYYMMDD（今天如果是周末则取周五）。"""
        d = date.today()
        # 简单处理：周末退到周五
        while d.weekday() >= 5:
            from datetime import timedelta
            d -= timedelta(days=1)
        return d.strftime('%Y%m%d')

    # ─── 限速调用 ─────────────────────────────────────

    def _call(self, func, **kwargs):
        """带限速的 Tushare API 调用，遇频率限制自动等待。"""
        if not self._available:
            raise RuntimeError("Tushare 不可用")
        self._bucket.consume()

        max_retries = 3
        for attempt in range(max_retries):
            try:
                return func(**kwargs)
            except Exception as e:
                err_str = str(e)
                if '频率' in err_str or 'frequency' in err_str.lower():
                    if attempt < max_retries - 1:
                        wait = 30 * (attempt + 1)  # 首次30s，二次60s
                        print(f"  [Tushare] 频率超限，等待 {wait}s 重试...", flush=True)
                        import time as _time
                        _time.sleep(wait)
                        continue
                print(f"  [Tushare] API 错误: {e}", flush=True)
                raise

    # ─── daily_basic: 全市场日线指标 ──────────────────

    def daily_basic(self, trade_date=None, force_refresh=False):
        """全市场 PE/PB/换手率/市值，每天只拉一次。

        返回 pd.DataFrame，含 ts_code, pe, pb, total_mv, turnover_rate 等。
        """
        if not self._available:
            return pd.DataFrame()

        cache_date = self._daily_basic_cache['date']
        today = self._last_trade_day()

        if not force_refresh and cache_date == today and self._daily_basic_cache['data'] is not None:
            return self._daily_basic_cache['data']

        trade_date = trade_date or today
        try:
            df = self._call(
                self._pro.daily_basic,
                trade_date=trade_date,
                fields='ts_code,trade_date,close,pe,pb,total_mv,circ_mv,turnover_rate,volume_ratio,pe_ttm'
            )
            if df is not None and len(df) > 0:
                self._daily_basic_cache = {'data': df, 'date': trade_date}
                print(f"  [Tushare] daily_basic: {len(df)} 只股票 ({trade_date})")
            return df if df is not None else pd.DataFrame()
        except Exception as e:
            print(f"  [Tushare] daily_basic 失败: {e}")
            # 返回旧缓存
            return self._daily_basic_cache['data'] or pd.DataFrame()

    def get_quote_batch(self):
        """获取全市场报价数据：返回 dict {code: {pe, pb, total_mv}}。"""
        df = self.daily_basic()
        if df.empty:
            return {}
        result = {}
        for _, row in df.iterrows():
            ts_code = str(row.get('ts_code', ''))
            code = ts_code.split('.')[0]  # '000001.SZ' → '000001'
            result[code] = {
                'pe': row.get('pe'),
                'pb': row.get('pb'),
                'total_mv': row.get('total_mv'),
                'circ_mv': row.get('circ_mv'),
                'turnover_rate': row.get('turnover_rate'),
                'close': row.get('close'),
            }
        return result

    def get_stock_name(self, code):
        """获取股票中文名称。"""
        if not self._available:
            return ''
        market = 'SH' if code.startswith('6') else 'SZ'
        ts_code = f"{code}.{market}"
        try:
            df = self._call(
                self._pro.stock_basic,
                ts_code=ts_code,
                fields='ts_code,name'
            )
            if df is not None and len(df) > 0:
                return str(df.iloc[0]['name'])
        except:
            pass
        return ''

    def get_stock_names_batch(self, codes):
        """批量获取股票名称，返回 {code: name}。"""
        names = {}
        for code in codes:
            name = self.get_stock_name(code)
            if name:
                names[code] = name
        return names

    # ─── fina_indicator: 基本面指标 ──────────────────

    def fina_indicator(self, code, years=1):
        """获取一只股票的基本面数据。

        code: 6位股票代码（如 '000001'）
        years: 查几年（默认1年）

        返回 {year: {roe, eps, ...}} 或 None。
        """
        if not self._available:
            return None

        # 构造 Tushare ts_code
        market = 'SH' if code.startswith('6') else 'SZ'
        ts_code = f"{code}.{market}"

        cache_key = code
        with self._fina_cache_lock:
            if cache_key in self._fina_cache:
                return self._fina_cache[cache_key]

        current_year = datetime.now().year
        start_year = current_year - years
        start_date = f"{start_year}0101"
        end_date = f"{current_year}1231"

        try:
            df = self._call(
                self._pro.fina_indicator,
                ts_code=ts_code,
                start_date=start_date,
                end_date=end_date,
                fields=(
                    'ts_code,end_date,roe,eps,roe_waa,ocfps,'
                    'grossprofit_margin,netprofit_margin,profit_dedt,'
                    'debt_to_assets,current_ratio,quick_ratio,'
                    'ocf_to_or,ebit_to_interest,'
                    'netprofit_yoy,or_yoy,'
                    'total_assets,total_liab,total_hldr_eqy_exc_min_int,'
                    'assets_turn,ar_turn'
                )
            )
            if df is None or len(df) == 0:
                return None

            # 去重：保留每个年度的年报数据（end_date 的月份=12）
            # 取最新年份的Q4数据
            result = {}
            for _, row in df.iterrows():
                end_date_str = str(row.get('end_date', ''))
                if len(end_date_str) >= 4:
                    year = end_date_str[:4]
                    month = end_date_str[4:6] if len(end_date_str) >= 6 else ''
                    # 优先用年报（12月）、其次季报
                    if month in ('12', '') or year not in result:
                        entry = {k: self._to_float(row.get(k))
                                 for k in row.keys()
                                 if k not in ('ts_code', 'end_date')}
                        entry['end_date'] = end_date_str
                        result[year] = entry

            with self._fina_cache_lock:
                self._fina_cache[cache_key] = result
            return result

        except Exception as e:
            print(f"  [Tushare] fina_indicator {code} 失败: {e}")
            return None

    def batch_fina_indicator(self, codes, years=1, progress_callback=None):
        """批量获取多只股票基本面数据。

        codes: 股票代码列表 ['000001', '000002', ...]
        years: 查几年
        progress_callback(code, index, total): 可选进度回调

        返回 {code: {year: {fields}}} 字典。
        """
        result = {}
        total = len(codes)
        for i, code in enumerate(codes):
            if progress_callback:
                progress_callback(code, i + 1, total)
            data = self.fina_indicator(code, years=years)
            if data:
                result[code] = data
        return result

    @staticmethod
    def _to_float(val):
        if val is None or val == '':
            return None
        try:
            return float(val)
        except (ValueError, TypeError):
            return None

    # ─── 批量导出为 fundamentals_loader 格式 ─────────

    def export_fundamentals(self, codes, years=1):
        """批量采集并导出为 fundamentals_loader 兼容格式。

        返回可直接写入 fundamentals_complete.json 的字典。
        """
        stocks = {}
        total = len(codes)

        for i, code in enumerate(codes):
            print(f"  [{i+1}/{total}] {code}...", end='', flush=True)
            data = self.fina_indicator(code, years=years)
            if not data:
                print(" 无数据")
                continue

            # 重组为 {year: {field: val}} 格式
            years_dict = {}
            for yr, entry in data.items():
                year_data = {}
                map_fields = {
                    'roe': 'roe', 'eps': 'eps',
                    'grossprofit_margin': 'gp_margin', 'netprofit_margin': 'np_margin',
                    'profit_dedt': 'profit_dedt',
                    'debt_to_assets': 'liab_ratio',
                    'current_ratio': 'current_ratio', 'quick_ratio': 'quick_ratio',
                    'ebit_to_interest': 'ebit_to_interest',
                    'ocf_to_or': 'cfo_to_or',
                    'netprofit_yoy': 'profit_growth', 'or_yoy': 'revenue_growth',
                    'assets_turn': 'asset_turnover', 'ar_turn': 'ar_turnover',
                }
                for our_key, src_key in map_fields.items():
                    if src_key and src_key in entry and entry[src_key] is not None:
                        year_data[our_key] = entry[src_key]

                # Tushare返回百分比值，转换为小数
                for pf in ['roe', 'gp_margin', 'np_margin', 'liab_ratio',
                            'profit_growth', 'revenue_growth']:
                    if pf in year_data and year_data[pf] is not None:
                        year_data[pf] = year_data[pf] / 100.0

                # 计算 asset_to_equity
                ta = entry.get('total_assets')
                eq = entry.get('total_hldr_eqy_exc_min_int')
                if ta and eq and eq > 0:
                    year_data['asset_to_equity'] = ta / eq

                if year_data:
                    years_dict[yr] = year_data
                    print(f" {yr}: ROE={year_data.get('roe', '?')}", end='', flush=True)

            if years_dict:
                market = 'sh' if code.startswith('6') else 'sz'
                entry = {
                    'code': code,
                    'market': market,
                    'name': '',
                    'industry': '',
                    'updated': date.today().isoformat(),
                    'years': years_dict,
                }
                stocks[code] = entry
                print(" ✓")
            else:
                print(" 无有效数据")

        return {
            'stocks': stocks,
            'meta': {
                'total_stocks': len(stocks),
                'updated': date.today().isoformat(),
                'source': 'tushare',
            }
        }


# ─── 单例 ──────────────────────────────────────────────

_global_provider = None
_global_lock = threading.Lock()


def get_provider():
    global _global_provider
    if _global_provider is None:
        with _global_lock:
            if _global_provider is None:
                _global_provider = TushareProvider()
    return _global_provider


def reset_provider():
    """强制重建（环境变量改变时调用）。"""
    global _global_provider
    with _global_lock:
        _global_provider = TushareProvider()
