#!/usr/bin/env python3
"""财报排雷数据 - Baostock版（免Tushare Token）

Baostock 免费接口，获取A股财务数据用于排雷分析。
输出 JSON 到 stdout。

Usage:
    python3 minesweeper_baostock.py --stock-code 603993 [--years 3]
"""

import argparse
import json
import sys
import datetime

try:
    import baostock as bs
except ImportError:
    print(json.dumps({"error": "baostock 未安装，请执行 pip install baostock"}))
    sys.exit(1)


def _free(rs):
    try:
        rs.free()
    except:
        pass


def _to_num(val):
    if val == "" or val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return val


def query_year(code, year, query_func, label):
    """Query Q4 data, returns dict {field: value} or None."""
    try:
        rs = query_func(code, year, 4)
        if rs.error_code != "0":
            print(f"  ⚠ {label} {year}: {rs.error_msg}", file=sys.stderr)
            return None
        rows = rs.data
        _free(rs)
        if rows and len(rows) > 0:
            row = rows[0]
            return {rs.fields[i]: _to_num(row[i]) for i in range(min(len(rs.fields), len(row)))}
        return None
    except Exception as e:
        print(f"  ⚠ {label} {year}: {e}", file=sys.stderr)
        return None


def _silent_login():
    """Suppress baostock login/logout stdout chatter."""
    old_out = sys.stdout
    sys.stdout = sys.stderr
    lg = bs.login()
    sys.stdout = old_out
    return lg

def collect_minesweeper_data(stock_code, years=3):
    """Fetch financial data using Baostock (free)."""
    code = f"sh.{stock_code}" if stock_code.startswith("6") else f"sz.{stock_code}"
    current_year = datetime.datetime.now().year
    year_range = range(current_year - years, current_year + 1)

    _silent_login()
    try:
        # ── 1. Basic info ──
        print("  [1/7] 基本信息...", file=sys.stderr)
        stock_info = {"code": code, "name": "", "industry": "", "ipo_date": ""}
        rs = bs.query_stock_basic(code)
        if rs.error_code == "0" and rs.data:
            row = rs.data[0]
            stock_info = {
                "code": str(row[0]) if len(row) > 0 else code,
                "name": str(row[1]) if len(row) > 1 else "",
                "ipo_date": str(row[2]) if len(row) > 2 else "",
                "status": str(row[5]) if len(row) > 5 else "",
            }
        _free(rs)

        rs = bs.query_stock_industry(code)
        if rs.error_code == "0" and rs.data:
            row = rs.data[0]
            if len(row) > 3:
                stock_info["industry"] = str(row[3])
        _free(rs)

        # ── 2. Profitability ──
        print("  [2/7] 盈利能力...", file=sys.stderr)
        profit_data = []
        for y in year_range:
            d = query_year(code, y, bs.query_profit_data, "盈利能力")
            if d:
                d["year"] = y
                profit_data.append(d)

        # ── 3. Balance / Debt ──
        print("  [3/7] 偿债能力...", file=sys.stderr)
        debt_data = []
        for y in year_range:
            d = query_year(code, y, bs.query_balance_data, "偿债能力")
            if d:
                d["year"] = y
                debt_data.append(d)

        # ── 4. Operation ──
        print("  [4/7] 营运能力...", file=sys.stderr)
        oper_data = []
        for y in year_range:
            d = query_year(code, y, bs.query_operation_data, "营运能力")
            if d:
                d["year"] = y
                oper_data.append(d)

        # ── 5. Growth ──
        print("  [5/7] 成长能力...", file=sys.stderr)
        growth_data = []
        for y in year_range:
            d = query_year(code, y, bs.query_growth_data, "成长能力")
            if d:
                d["year"] = y
                growth_data.append(d)

        # ── 6. Cash flow ──
        print("  [6/7] 现金流...", file=sys.stderr)
        cf_data = []
        for y in year_range:
            d = query_year(code, y, bs.query_cash_flow_data, "现金流")
            if d:
                d["year"] = y
                cf_data.append(d)

        # ── 7. DuPont ──
        print("  [7/7] 杜邦分析...", file=sys.stderr)
        dupont_data = []
        for y in year_range:
            d = query_year(code, y, bs.query_dupont_data, "杜邦分析")
            if d:
                d["year"] = y
                dupont_data.append(d)

        # ── Combined ──
        combined = []
        for y in year_range:
            entry = {"year": y}
            for src in (profit_data, debt_data, growth_data):
                for item in src:
                    if item["year"] == y:
                        entry.update({k: v for k, v in item.items() if k != "year" and v is not None})
            if len(entry) > 1:
                combined.append(entry)

        return {
            "stock_info": stock_info,
            "data_source": "baostock",
            "audit": [],
            "profit": profit_data,
            "debt": debt_data,
            "operation": oper_data,
            "growth": growth_data,
            "cashflow": cf_data,
            "dupont": dupont_data,
            "indicators": combined,
            "note": "数据来源: Baostock（免费）",
        }

    finally:
        old_out = sys.stdout
        sys.stdout = sys.stderr
        bs.logout()
        sys.stdout = old_out


def main():
    parser = argparse.ArgumentParser(description="Baostock 版排雷数据采集")
    parser.add_argument("--stock-code", required=True, help="股票代码，如 603993")
    parser.add_argument("--years", type=int, default=3, help="年数（默认3）")
    args = parser.parse_args()

    try:
        data = collect_minesweeper_data(args.stock_code, args.years)
        print(json.dumps(data, ensure_ascii=False, indent=2))
    except Exception as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False))
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
