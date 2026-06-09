"""估值分析引擎 — 自算 PE/PB vs 市场报价对比"""
import json
import os
import sys
from datetime import datetime

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')


def _to_num(val):
    if val == "" or val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return val


def finance_data(code, years=3):
    """通过 baostock 获取财报数据"""
    import baostock as bs
    market = 'sh' if code.startswith('6') else 'sz'
    full_code = f'{market}.{code}'
    current_year = datetime.now().year
    year_range = range(current_year - years, current_year + 1)

    old_out = sys.stdout
    sys.stdout = sys.stderr
    lg = bs.login()
    sys.stdout = old_out
    if lg.error_code != '0':
        return None

    result = {'code': code, 'market': market}

    try:
        # 基本信息 + 行业
        rs = bs.query_stock_basic(full_code)
        if rs.error_code == '0' and rs.data:
            row = rs.data[0]
            result['name'] = str(row[1]) if len(row) > 1 else ''
        try:
            rs = bs.query_stock_industry(full_code)
            if rs.error_code == '0' and rs.data:
                row = rs.data[0]
                result['industry'] = str(row[3]) if len(row) > 3 else ''
        except:
            pass

        # 利润表: 仅取年报（Q4）数据，确保 epsTTM 和 roeAvg 都是全年口径
        eps_ttm = 0
        roe = 0
        total_share = 0
        for y in reversed(year_range):
            rs = bs.query_profit_data(full_code, y, 4)
            if rs.error_code == '0' and rs.data and rs.data[0]:
                row = rs.data[0]
                d = {rs.fields[i]: _to_num(row[i]) for i in range(min(len(rs.fields), len(row)))}
                if d.get('epsTTM', 0):
                    eps_ttm = d['epsTTM']
                    roe = d.get('roeAvg', 0) or 0
                    total_share = d.get('totalShare', 0) or 0
                    result['profit_year'] = y
                    result['profit_quarter'] = 4
                    break

        if eps_ttm:
            result['eps_ttm'] = eps_ttm
        if roe:
            result['roe'] = roe
        if total_share:
            result['total_share'] = total_share

        # DuPont 分析（用于辅助计算BVPS）
        if not roe:
            rs = bs.query_dupont_data(full_code, current_year - 1, 4)
            if rs.error_code == '0' and rs.data:
                row = rs.data[0]
                d = {rs.fields[i]: _to_num(row[i]) for i in range(min(len(rs.fields), len(row)))}
                roe = d.get('dupontROE', 0) or 0
                if roe and not result.get('roe'):
                    result['roe'] = roe

    finally:
        bs.logout()

    return result


def get_valuation(code, price, market_pe=None, market_pb=None):
    """综合估值分析"""
    fd = finance_data(code)
    if not fd:
        return {'error': '无法获取财务数据'}

    result = {
        'code': code,
        'name': fd.get('name', ''),
        'industry': fd.get('industry', ''),
        'market_pe': round(market_pe, 2) if market_pe else None,
        'market_pb': round(market_pb, 2) if market_pb else None,
    }

    # 自算 TTM PE
    eps = fd.get('eps_ttm', 0)
    if eps and eps > 0:
        ttm_pe = price / eps
        result['ttm_pe'] = round(ttm_pe, 2)
        if market_pe and market_pe > 0:
            result['pe_deviation_pct'] = round((ttm_pe - market_pe) / market_pe * 100, 1)
    else:
        result['ttm_pe'] = None

    # 自算 PB: BVPS = eps / ROE, PB = price / BVPS
    roe = fd.get('roe', 0)
    if eps and eps > 0 and roe and roe > 0:
        bvps = eps / roe
        pb_self = price / bvps
        result['pb'] = round(pb_self, 2)
        if market_pb and market_pb > 0:
            result['pb_deviation_pct'] = round((pb_self - market_pb) / market_pb * 100, 1)
    else:
        result['pb'] = None

    # ROE
    if roe:
        result['roe'] = round(roe * 100, 1)  # 转为百分比

    # 备注
    notes = []
    ttm_pe = result.get('ttm_pe')
    pe_dev = result.get('pe_deviation_pct')
    pb_dev = result.get('pb_deviation_pct')
    if ttm_pe and market_pe:
        if pe_dev and pe_dev < -15:
            notes.append(f"自算PE比市场低{abs(pe_dev):.0f}%，财报盈利可能被市场低估")
        elif pe_dev and pe_dev > 15:
            notes.append(f"自算PE比市场高{pe_dev:.0f}%，市场报价包含预期溢价或财报已滞后")
    if result.get('pb') and market_pb:
        if pb_dev and pb_dev < -15:
            notes.append(f"自算PB比市场低{abs(pb_dev):.0f}%，每股净资产可能被低估")
        elif pb_dev and pb_dev > 15:
            notes.append(f"自算PB比市场高{pb_dev:.0f}%，存在资产溢价")
    result['notes'] = notes

    return result
