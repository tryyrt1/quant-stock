"""基本面数据加载器 — 从本地 JSON 文件加载缓存好的财务数据

用法:
    from engine.fundamentals_loader import FundamentalsLoader
    fl = FundamentalsLoader()
    data = fl.get('600519')
    if data:
        roe = fl.get_roe(data)
        liab = fl.get_liab_ratio(data)
"""

import json
import os
import threading

# 项目 data 目录
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')
FUND_FILE = os.path.join(DATA_DIR, 'fundamentals', 'fundamentals_complete.json')


class FundamentalsLoader:
    """懒加载 + 缓存基本面数据，提供便捷查询方法。"""

    def __init__(self, filepath=None):
        self._filepath = filepath or FUND_FILE
        self._data = None       # {code: {code, name, years: {year: {fields}}}}
        self._meta = None
        self._lock = threading.Lock()
        self._loaded = False

    # ─── 加载 ───────────────────────────────────────

    def _ensure_loaded(self):
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            self._do_load()

    def _do_load(self):
        if not os.path.exists(self._filepath):
            self._data = {}
            self._meta = {}
            self._loaded = True
            return
        try:
            with open(self._filepath, 'r', encoding='utf-8') as f:
                raw = json.load(f)
            self._data = raw.get('stocks', {})
            self._meta = raw.get('meta', {})
        except Exception:
            self._data = {}
            self._meta = {}
        self._loaded = True

    def reload(self):
        """强制重新加载（文件更新后调用）。"""
        with self._lock:
            self._loaded = False
            self._do_load()

    # ─── 查询接口 ───────────────────────────────────

    def get(self, code):
        """按 6 位代码获取一只股票的全部基本面数据，或 None。"""
        self._ensure_loaded()
        return self._data.get(code)

    def get_raw(self):
        """获取全部数据字典 {code: entry}。"""
        self._ensure_loaded()
        return self._data

    def get_meta(self):
        """获取 meta 信息。"""
        self._ensure_loaded()
        return self._meta

    def is_available(self):
        """是否有基本面数据可用。"""
        self._ensure_loaded()
        return len(self._data) > 0

    def total_stocks(self):
        """有多少只股票有数据。"""
        self._ensure_loaded()
        return len(self._data)

    # ─── 便捷字段提取 ───────────────────────────────

    def get_latest_year(self, data):
        """返回最新年份的字段 dict，或 None。"""
        years = data.get('years', {}) if data else {}
        if not years:
            return None
        latest = max(years.keys())
        return years[latest]

    def get_year(self, data, year):
        """返回指定年份的字段 dict，或 None。"""
        years = data.get('years', {}) if data else {}
        return years.get(str(year)) or years.get(year)

    def get_roe(self, data):
        """最新 ROE（小数，如 0.15 = 15%），或 None。"""
        yr = self.get_latest_year(data)
        if yr is None:
            return None
        # 优先用 profit 的 roe，回退 dupont_roe
        return yr.get('roe') or yr.get('dupont_roe')

    def get_liab_ratio(self, data):
        """负债率（小数，如 0.5 = 50%），修正 baostock 已知异常。"""
        yr = self.get_latest_year(data)
        if yr is None:
            return None

        raw = yr.get('liab_ratio')
        asset_to_eq = yr.get('asset_to_equity')

        # baostock 的 liabilityToAsset 对部分股票（如银行、地产）不可靠
        # 可靠性判断: 合理的负债率应在 0.02 ~ 0.98 之间
        if raw is not None and 0.02 <= raw <= 0.98:
            return raw

        # 从权益乘数推导: 负债率 = 1 - 1/assetToEquity
        if asset_to_eq is not None and asset_to_eq > 1:
            derived = 1.0 - (1.0 / asset_to_eq)
            if 0.02 <= derived <= 0.98:
                return derived

        # 兜底返回原始值（可能是 None 或异常值）
        return raw

    def get_eps(self, data):
        """最新 EPS。"""
        yr = self.get_latest_year(data)
        return yr.get('eps') if yr else None

    def get_net_profit(self, data):
        """最新净利润。"""
        yr = self.get_latest_year(data)
        return yr.get('net_profit') if yr else None

    def get_gp_margin(self, data):
        """最新毛利率（小数）。"""
        yr = self.get_latest_year(data)
        return yr.get('gp_margin') if yr else None

    def get_np_margin(self, data):
        """最新净利率（小数）。"""
        yr = self.get_latest_year(data)
        return yr.get('np_margin') if yr else None

    def get_quick_ratio(self, data):
        """最新速动比率。"""
        yr = self.get_latest_year(data)
        return yr.get('quick_ratio') if yr else None

    def get_profit_growth(self, data):
        """最新净利润同比增长率（小数）。"""
        yr = self.get_latest_year(data)
        return yr.get('profit_growth') if yr else None

    def get_revenue_growth(self, data):
        """最新营收同比增长率（小数）。"""
        yr = self.get_latest_year(data)
        return yr.get('revenue_growth') if yr else None

    def get_ebit_to_interest(self, data):
        """最新利息保障倍数。"""
        yr = self.get_latest_year(data)
        return yr.get('ebit_to_interest') if yr else None

    # ─── 多年度辅助 ────────────────────────────────

    def get_roe_history(self, data, years=3):
        """返回 ROE 列表（最新在前），长度 <= years。"""
        if not data:
            return []
        yrs = data.get('years', {})
        sorted_y = sorted(yrs.keys(), reverse=True)[:years]
        vals = []
        for y in sorted_y:
            v = yrs[y].get('roe') or yrs[y].get('dupont_roe')
            if v is not None:
                vals.append(v)
        return vals

    def get_profit_growth_history(self, data, years=3):
        """返回净利润增长率列表（最新在前）。"""
        if not data:
            return []
        yrs = data.get('years', {})
        return [yrs[y].get('profit_growth') for y in sorted(yrs.keys(), reverse=True)[:years]
                if yrs[y].get('profit_growth') is not None]


# ─── 模块级单例 ───────────────────────────────────
_global_loader = None
_global_lock = threading.Lock()


def get_loader():
    """获取全局 FundamentalsLoader 单例。"""
    global _global_loader
    if _global_loader is None:
        with _global_lock:
            if _global_loader is None:
                _global_loader = FundamentalsLoader()
    return _global_loader


def get_fundamentals(code):
    """快捷方式: 获取一只股票的基本面数据。"""
    return get_loader().get(code)
