#!/usr/bin/env python3
"""A 股基本面数据批量采集 — 本地运行后传送到服务器

用法:
    python batch_fundamentals.py                        # 完整扫描（~1800只）
    python batch_fundamentals.py --max-stocks 50        # 测试用（只扫50只）
    python batch_fundamentals.py --resume               # 断点续传
    python batch_fundamentals.py --quiet                # 安静模式（只显示汇总）

依赖: pip install baostock

流程:
    1. 加载 data/all_stocks.json → 过滤活跃股
    2. 分批次查询 baostock → 每批写入 data/fundamentals/batch_NNN.json
    3. 全部完成 → 合并为 data/fundamentals/fundamentals_complete.json
"""

import argparse
import datetime
import json
import os
import sys
import time

try:
    import baostock as bs
except ImportError:
    print("需要安装 baostock: pip install baostock", file=sys.stderr)
    sys.exit(1)

# ─── 路径 ───────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
FUND_DIR = os.path.join(DATA_DIR, 'fundamentals')
STOCK_FILE = os.path.join(DATA_DIR, 'all_stocks.json')
PROGRESS_FILE = os.path.join(FUND_DIR, '_progress.json')


# ─── baostock 辅助 ──────────────────────────────────────

def _free(rs):
    try:
        rs.free()
    except Exception:
        pass


def _to_num(val):
    if val == "" or val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return val


def query_year(code, year, query_func, label):
    """查询指定年份 Q4（年报）数据，返回 dict 或 None。"""
    try:
        rs = query_func(code, year, 4)
        if rs.error_code != "0":
            return None
        rows = rs.data
        _free(rs)
        if rows and len(rows) > 0:
            row = rows[0]
            return {rs.fields[i]: _to_num(row[i]) for i in range(min(len(rs.fields), len(row)))}
        return None
    except Exception:
        return None


def silent_login():
    """静默登录 baostock（压制 stdout 输出）。"""
    old = sys.stdout
    sys.stdout = sys.stderr
    lg = bs.login()
    sys.stdout = old
    return lg


def silent_logout():
    old = sys.stdout
    sys.stdout = sys.stderr
    bs.logout()
    sys.stdout = old


def code_to_bs(code):
    """给 6 位代码加 baostock 前缀。"""
    return f"sh.{code}" if code.startswith("6") else f"sz.{code}"


# ─── 字段映射 ───────────────────────────────────────────

# 我们关心哪些 baostock 字段 → 标准化 key 名
FIELD_MAP = {
    # profit
    "roeAvg": "roe",
    "epsTTM": "eps",
    "netProfit": "net_profit",
    "gpMargin": "gp_margin",
    "npMargin": "np_margin",
    "profitDedt": "profit_dedt",
    # balance
    "liabilityToAsset": "liab_ratio",
    "assetToEquity": "asset_to_equity",  # 权益乘数，可推导真实负债率
    "currentRatio": "current_ratio",
    "quickRatio": "quick_ratio",
    # cashflow
    "CFOToOR": "cfo_to_or",
    "CFOToNP": "cfo_to_np",
    "ebitToInterest": "ebit_to_interest",
    # growth
    "YOYNI": "profit_growth",
    "YOYPNI": "revenue_growth",
    # dupont
    "dupontROE": "dupont_roe",
    "dupontAssetTurn": "asset_turnover",
}

# 查询计划: (label, query_func, raw_key_prefix)
QUERIES = [
    ("profit",     bs.query_profit_data),
    ("balance",    bs.query_balance_data),
    ("cashflow",   bs.query_cash_flow_data),
    ("growth",     bs.query_growth_data),
    ("dupont",     bs.query_dupont_data),
]


def extract_fields(raw_dict):
    """从 baostock 原始 dict 提取我们关心的字段，返回标准化 dict。"""
    result = {}
    for bs_key, our_key in FIELD_MAP.items():
        val = raw_dict.get(bs_key)
        if val is not None:
            result[our_key] = val
    return result


# ─── 股票过滤 ───────────────────────────────────────────

def load_and_filter_stocks():
    """加载 all_stocks.json 并应用和 fetch_a_share_list() 相同的过滤。"""
    if not os.path.exists(STOCK_FILE):
        print(f"[错误] 找不到 {STOCK_FILE}", file=sys.stderr)
        print("请先在 server.py 中运行 fetch_a_share_list() 生成此文件", file=sys.stderr)
        sys.exit(1)

    with open(STOCK_FILE, 'r', encoding='utf-8') as f:
        all_stocks = json.load(f)

    stocks = []
    for s in all_stocks:
        code = str(s.get('code', ''))
        name = str(s.get('name', ''))
        if s.get('market') == 'bj':
            continue
        if code.startswith('3') or code.startswith('688'):
            continue
        if 'ST' in name.upper() or '*' in name.upper():
            continue
        market = 'sh' if code.startswith('6') else 'sz'
        stocks.append({'code': code, 'market': market, 'name': name})

    stocks.sort(key=lambda x: x['code'])
    return stocks


# ─── 查询单只股票 ──────────────────────────────────────

def fetch_stock_data(bs_code, years=3):
    """获取一只股票历年基本面数据。返回 {year: {field: val}}。"""
    current_year = datetime.datetime.now().year
    year_range = range(current_year - years, current_year + 1)

    results = {}  # year -> merged dict

    for label, query_func in QUERIES:
        for y in year_range:
            raw = query_year(bs_code, y, query_func, label)
            if raw is None:
                continue
            extracted = extract_fields(raw)
            if not extracted:
                continue
            if y not in results:
                results[y] = {}
            results[y].update(extracted)

    return results


# ─── 进度显示 ──────────────────────────────────────────

class ProgressBar:
    def __init__(self, total, quiet=False):
        self.total = total
        self.done = 0
        self.success = 0
        self.fail = 0
        self.partial = 0
        self.quiet = quiet
        self.start_time = time.time()
        self.last_batch_time = time.time()
        self.batch_count = 0
        self._printed_header = False

    def _print(self, msg):
        if not self.quiet:
            ts = datetime.datetime.now().strftime("%H:%M:%S")
            print(f"[{ts}] {msg}", flush=True)

    def header(self):
        if not self.quiet and not self._printed_header:
            print(f"{'-' * 50}", flush=True)
            print(f"  A股基本面数据批量采集", flush=True)
            print(f"  股票总数: {self.total}", flush=True)
            print(f"{'-' * 50}", flush=True)
            self._printed_header = True

    def stock_start(self, code, name, market, query_label):
        self._print(f">> {code} {name} ({market}) -- 查询 {query_label}...")

    def stock_done(self, code, name, market, year_count, fields_count, has_warn=False):
        self.done += 1
        self.success += 1
        if has_warn:
            self.partial += 1
        pct = self.done * 100 // self.total
        elapsed = time.time() - self.start_time
        remaining = (elapsed / self.done) * (self.total - self.done) if self.done > 0 else 0
        elapsed_str = self._fmt_dur(elapsed)
        remain_str = self._fmt_dur(remaining)
        warn_mark = " !!" if has_warn else ""
        self._print(f"OK {code} {name} -- {year_count}年 {fields_count}字段{warn_mark}  [{self.done}/{self.total} {pct}%] "
                     f"已过{elapsed_str} 预估剩余{remain_str}")

    def stock_skip(self, code, name, market, reason):
        self.done += 1
        self.fail += 1
        self._print(f"XX {code} {name} -- 跳过 ({reason})")

    def batch_summary(self, batch_size, processed):
        self.batch_count += 1
        elapsed = time.time() - self.last_batch_time
        self.last_batch_time = time.time()
        total_elapsed = time.time() - self.start_time
        remain_total = (total_elapsed / processed) * (self.total - processed) if processed > 0 else 0
        self._print(f"{'-' * 50}")
        self._print(f"批次 #{self.batch_count} 完成 ({batch_size}只, 耗时{self._fmt_dur(elapsed)}, "
                     f"累计{processed}/{self.total}, 预估总剩余{self._fmt_dur(remain_total)})")
        self._print(f"  成功: {self.success}  |  部分缺失: {self.partial}  |  失败: {self.fail}")
        self._print(f"{'-' * 50}")

    def summary(self):
        total_elapsed = time.time() - self.start_time
        print(f"\n{'=' * 50}", flush=True)
        print(f"  采集完成!", flush=True)
        print(f"  总耗时: {self._fmt_dur(total_elapsed)}", flush=True)
        print(f"  成功: {self.success}  |  部分缺失: {self.partial}  |  失败: {self.fail}", flush=True)
        print(f"{'=' * 50}", flush=True)

    @staticmethod
    def _fmt_dur(seconds):
        seconds = int(seconds)
        h, m = divmod(seconds, 3600)
        m, s = divmod(m, 60)
        if h:
            return f"{h}h{m:02d}m"
        elif m:
            return f"{m}m{s:02d}s"
        return f"{s}s"


# ─── 批处理逻辑 ────────────────────────────────────────

def load_progress():
    """读取进度文件，返回已完成股票代码的 set。"""
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, 'r') as f:
                data = json.load(f)
            return set(data.get('completed', []))
        except Exception:
            pass
    return set()


def save_progress(completed_set):
    """保存进度文件。"""
    os.makedirs(FUND_DIR, exist_ok=True)
    with open(PROGRESS_FILE, 'w') as f:
        json.dump({'completed': sorted(completed_set)}, f, ensure_ascii=False)


def main():
    parser = argparse.ArgumentParser(description="A 股基本面数据批量采集")
    parser.add_argument('--max-stocks', type=int, default=0,
                        help='限制采集数量（调试用，默认全部）')
    parser.add_argument('--batch-size', type=int, default=50,
                        help='每批多少只股票后重连（默认50）')
    parser.add_argument('--years', type=int, default=3,
                        help='查询几年数据（默认3年）')
    parser.add_argument('--resume', action='store_true',
                        help='从上次进度继续')
    parser.add_argument('--quiet', action='store_true',
                        help='安静模式，只显示汇总')
    parser.add_argument('--no-merge', action='store_true',
                        help='不合并批文件')
    parser.add_argument('--source', default='baostock', choices=['baostock', 'tushare'],
                        help='数据源: baostock(慢但免费) / tushare(快需Token)')
    args = parser.parse_args()

    # 1. 加载股票列表
    stocks = load_and_filter_stocks()
    if args.max_stocks and args.max_stocks < len(stocks):
        stocks = stocks[:args.max_stocks]

    total = len(stocks)
    if total == 0:
        print("没有符合条件的股票", file=sys.stderr)
        return

    progress = ProgressBar(total, quiet=args.quiet)
    progress.header()

    # 2. 断点续传
    completed = load_progress() if args.resume else set()
    if completed:
        skip_count = sum(1 for s in stocks if s['code'] in completed)
        progress._print(f"断点续传: {len(completed)} 只已完成，跳过 {skip_count} 只")
        stocks = [s for s in stocks if s['code'] not in completed]

    if not stocks:
        progress._print("全部股票已完成!")
        return

    # ─── Tushare 数据源 ─────────────────────────────
    if args.source == 'tushare':
        progress._print("使用 Tushare Pro 数据源")
        os.environ['TUSHARE_TOKEN'] = os.environ.get('TUSHARE_TOKEN', '')
        from engine.tushare_provider import TushareProvider
        tp = TushareProvider()
        if not tp.available:
            progress._print("[错误] Tushare 不可用，请设置 TUSHARE_TOKEN 环境变量")
            sys.exit(1)

        codes = [s['code'] for s in stocks]
        total = len(codes)
        progress._print(f"开始采集 {total} 只股票，限速 200次/分钟...")

        # 预取名称
        progress._print("正在获取股票名称...")
        name_cache = {}
        for code in codes[:50]:
            n = tp.get_stock_name(code)
            if n: name_cache[code] = n

        # 逐只采集
        all_data = {}
        for i, code in enumerate(codes):
            pct = (i + 1) * 100 // total
            data = tp.fina_indicator(code, years=args.years)
            if data:
                # 重组为输出格式
                years_dict = {}
                for yr, entry in data.items():
                    year_data = {}
                    field_map = {
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
                    for src_key, our_key in field_map.items():
                        val = entry.get(src_key)
                        if val is not None:
                            year_data[our_key] = val

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

                if years_dict:
                    market = 'sh' if code.startswith('6') else 'sz'
                    all_data[code] = {
                        'code': code,
                        'market': market,
                        'name': name_cache.get(code, ''),
                        'updated': datetime.date.today().isoformat(),
                        'years': years_dict,
                    }
                    progress._print(f"  [{i+1}/{total} {pct}%] {code} - OK ({len(years_dict)}年)")
                else:
                    progress._print(f"  [{i+1}/{total} {pct}%] {code} - 无财务数据")
            else:
                progress._print(f"  [{i+1}/{total} {pct}%] {code} - 采集失败")

            progress.done = i + 1
            progress.success = len(all_data)

        # 保存合并结果
        os.makedirs(FUND_DIR, exist_ok=True)
        output = {
            'stocks': all_data,
            'meta': {
                'total_stocks': len(all_data),
                'updated': datetime.date.today().isoformat(),
                'source': 'tushare',
                'data_quality': {
                    'success_count': len(all_data),
                    'partial_count': 0,
                    'failed_count': total - len(all_data),
                },
            },
        }
        complete_file = os.path.join(FUND_DIR, 'fundamentals_complete.json')
        with open(complete_file, 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        file_size = os.path.getsize(complete_file)
        progress._print(f"保存完成: {complete_file} ({file_size/1024:.0f}KB, {len(all_data)} 只)")
        progress.summary()
        return

    # ─── Baostock 数据源 ───────────────────────────
    # 3. 分批次采集
    os.makedirs(FUND_DIR, exist_ok=True)
    batch_num = 0
    processed = 0
    all_completed_codes = set(completed)

    for i in range(0, len(stocks), args.batch_size):
        batch = stocks[i:i + args.batch_size]
        batch_num += 1
        batch_file = os.path.join(FUND_DIR, f'fundamentals_batch_{batch_num:03d}.json')
        batch_data = {}

        # 登录
        lg = silent_login()
        if lg.error_code != '0':
            print(f"[错误] baostock 登录失败: {lg.error_msg}", file=sys.stderr)
            # 保存进度并退出
            save_progress(all_completed_codes)
            sys.exit(1)

        try:
            for s in batch:
                code = s['code']
                bs_code = code_to_bs(code)

                # 查询名称
                name = s['name']
                try:
                    rs = bs.query_stock_basic(bs_code)
                    if rs.error_code == '0' and rs.data:
                        row = rs.data[0]
                        name = str(row[1]) if len(row) > 1 else name
                    _free(rs)

                    rs = bs.query_stock_industry(bs_code)
                    if rs.error_code == '0' and rs.data:
                        row = rs.data[0]
                        if len(row) > 3:
                            industry = str(row[3])
                        else:
                            industry = ""
                    else:
                        industry = ""
                    _free(rs)
                except Exception:
                    industry = ""

                progress.stock_start(code, name, s['market'], "profit")

                # 查询 5 类财务数据
                years_data = fetch_stock_data(bs_code, years=args.years)

                if not years_data:
                    progress.stock_skip(code, name, s['market'], "无财务数据")
                    continue

                # 组装每只股票的数据
                total_fields = 0
                years_dict = {}
                for yr in sorted(years_data.keys()):
                    years_dict[str(yr)] = years_data[yr]
                    total_fields += len(years_data[yr])

                entry = {
                    "code": code,
                    "market": s['market'],
                    "name": name,
                    "industry": industry,
                    "updated": datetime.date.today().isoformat(),
                    "years": years_dict,
                }
                batch_data[code] = entry
                all_completed_codes.add(code)

                # 检查是否有缺失字段（部分数据）
                has_warn = False
                first_year = list(years_data.values())[0]
                # 检查关键字段是否缺失
                for key in ['roe', 'gp_margin', 'liab_ratio']:
                    if key not in first_year:
                        has_warn = True
                        break

                progress.stock_done(code, name, s['market'],
                                    len(years_data), total_fields, has_warn=has_warn)
                processed += 1

        finally:
            silent_logout()

        # 保存本批次
        with open(batch_file, 'w', encoding='utf-8') as f:
            json.dump(batch_data, f, ensure_ascii=False)
        progress.batch_summary(len(batch), processed)

        # 保存进度（每批都保存，支持断点续传）
        save_progress(all_completed_codes)

    # 4. 合并所有批文件
    if not args.no_merge:
        merge_output(total, progress)

    progress.summary()


def merge_output(total, progress):
    """将 data/fundamentals/ 下的批文件合并为一个 complete.json。"""
    batch_files = sorted([
        f for f in os.listdir(FUND_DIR)
        if f.startswith('fundamentals_batch_') and f.endswith('.json')
    ])

    if not batch_files:
        return

    progress._print("正在合并批文件...")
    all_stocks = {}
    success_count = 0
    partial_count = 0
    fail_count = 0

    for bf in batch_files:
        path = os.path.join(FUND_DIR, bf)
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            for code, entry in data.items():
                all_stocks[code] = entry
                success_count += 1
                # 检查部分缺失
                years = entry.get('years', {})
                if years:
                    first_yr = list(years.values())[0]
                    if 'roe' not in first_yr:
                        partial_count += 1
        except Exception as e:
            print(f"  合并 {bf} 失败: {e}", file=sys.stderr)
            fail_count += 1

    output = {
        "stocks": all_stocks,
        "meta": {
            "total_stocks": len(all_stocks),
            "updated": datetime.date.today().isoformat(),
            "source": "baostock",
            "data_quality": {
                "success_count": success_count,
                "partial_count": partial_count,
                "failed_count": fail_count,
            },
        },
    }

    complete_file = os.path.join(FUND_DIR, 'fundamentals_complete.json')
    with open(complete_file, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    file_size = os.path.getsize(complete_file)
    file_size_str = f"{file_size / 1024 / 1024:.1f}MB" if file_size > 1024 * 1024 else f"{file_size / 1024:.0f}KB"
    progress._print(f"合并完成: {complete_file} ({file_size_str}, {len(all_stocks)} 只股票)")


if __name__ == '__main__':
    main()
