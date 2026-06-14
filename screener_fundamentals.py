#!/usr/bin/env python3
"""基本面筛选器 — 从 3030 只股票中选出 200 只候选股

用法:
    python screener_fundamentals.py                     # 默认条件筛选
    python screener_fundamentals.py --roe 10            # 自定义 ROE>=10%
    python screener_fundamentals.py --count 300         # 补足到 300 只
    python screener_fundamentals.py --show              # 只显示结果不保存

数据流:
    本地: screener_fundamentals.py → data/candidates.json (200只)
         ↓ SCP
    服务器: 读取 candidates.json → 盘中实时监控这 200 只
"""

import argparse
import json
import os
import sys
from datetime import date

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
FUND_FILE = os.path.join(DATA_DIR, 'fundamentals', 'fundamentals_complete.json')
OUTPUT_FILE = os.path.join(DATA_DIR, 'candidates.json')


def load_fundamentals():
    if not os.path.exists(FUND_FILE):
        print(f"[错误] 找不到 {FUND_FILE}", file=sys.stderr)
        print("请先运行 batch_fundamentals.py 采集基本面数据", file=sys.stderr)
        sys.exit(1)
    with open(FUND_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data['stocks']


def extract_latest(stocks_dict):
    """提取每只股票最新一年的数据，返回 [{code, name, roe, liab, gp, growth, ...}]"""
    results = []
    for code, s in stocks_dict.items():
        years = s.get('years', {})
        if not years:
            continue
        latest_year = max(years.keys())
        d = years[latest_year]
        results.append({
            'code': code,
            'market': s.get('market', 'sh' if code.startswith('6') else 'sz'),
            'name': s.get('name', ''),
            'roe': d.get('roe'),
            'liab_ratio': d.get('liab_ratio'),
            'gp_margin': d.get('gp_margin'),
            'profit_growth': d.get('profit_growth'),
            'revenue_growth': d.get('revenue_growth'),
            'eps': d.get('eps'),
            'current_ratio': d.get('current_ratio'),
            'quick_ratio': d.get('quick_ratio'),
            'cfo_to_np': d.get('cfo_to_np'),
        })
    return results


def screen(stocks, min_roe=0.075, max_liab=0.50, min_gp=0.20, min_growth=0.10, target_count=200):
    """多轮筛选：硬条件 → 逐步放宽 → 取前 target_count。"""

    def apply_filters(roe_min, liab_max, gp_min, growth_min):
        hits = []
        for s in stocks:
            if s['roe'] is None or s['liab_ratio'] is None:
                continue
            if s['roe'] < roe_min:
                continue
            if s['liab_ratio'] > liab_max:
                continue
            if gp_min > 0 and (s['gp_margin'] is None or s['gp_margin'] < gp_min):
                continue
            if growth_min > 0 and (s['profit_growth'] is None or s['profit_growth'] < growth_min):
                continue
            # 综合评分用于排序
            score = (
                min(s['roe'] / 0.20, 1.0) * 40 +        # ROE 越高越好
                max(1 - s['liab_ratio'] / 1.0, 0) * 25 +  # 负债越低越好
                min((s['gp_margin'] or 0) / 0.40, 1.0) * 20 +  # 毛利率越高越好
                min((s['profit_growth'] or 0) / 0.20, 1.0) * 15  # 增长越高越好
            )
            s['_score'] = round(score, 1)
            hits.append(s)
        hits.sort(key=lambda x: -x['_score'])
        return hits

    # 第1轮：硬条件
    result = apply_filters(min_roe, max_liab, min_gp, min_growth)
    rounds = [{'round': 1, 'desc': f'ROE>{min_roe*100:.1f}% + 负债<{max_liab*100:.0f}% + 毛利率>{min_gp*100:.0f}% + 增长>{min_growth*100:.0f}%', 'count': len(result)}]

    # 第2轮：放宽增长 > 0%
    if len(result) < target_count:
        result = apply_filters(min_roe, max_liab, min_gp, 0)
        rounds.append({'round': 2, 'desc': '放宽 增长>0%', 'count': len(result)})

    # 第3轮：放宽毛利率 > 10%
    if len(result) < target_count:
        result = apply_filters(min_roe, max_liab, 0.10, 0)
        rounds.append({'round': 3, 'desc': '放宽 毛利率>10%', 'count': len(result)})

    # 第4轮：放宽负债率 < 65%
    if len(result) < target_count:
        result = apply_filters(min_roe, 0.65, 0.10, 0)
        rounds.append({'round': 4, 'desc': '放宽 负债<65%', 'count': len(result)})

    # 第5轮：只保留 ROE
    if len(result) < target_count:
        result = apply_filters(min_roe, 1.0, 0, 0)
        rounds.append({'round': 5, 'desc': '仅保留 ROE条件', 'count': len(result)})

    # 第6轮：所有条件全放，按综合评分取前 target_count（高负债降序靠后）
    if len(result) < target_count:
        for s in stocks:
            roe = s['roe'] or 0
            liab = s['liab_ratio'] or 1
            gp = s['gp_margin'] or 0
            growth = s['profit_growth'] or 0
            # 综合评分：ROE(40) + 低负债奖励(25) + 毛利率(20) + 增长(15)
            s['_score'] = round(
                min(roe / 0.20, 1.0) * 40 +
                max(1 - liab / 1.0, 0) * 25 +
                min(gp / 0.40, 1.0) * 20 +
                min(growth / 0.20, 1.0) * 15, 1)
        stocks.sort(key=lambda x: -x['_score'])
        result = stocks[:target_count]
        rounds.append({'round': 6, 'desc': '全部放开，按综合评分取前{}只'.format(target_count), 'count': len(result)})

    # 最终排序：综合评分降序（高负债自动靠后）
    result.sort(key=lambda x: -x['_score'])

    final = result[:target_count]

    # 输出筛选过程
    print(f"\n{'=' * 50}")
    print(f"  筛选过程")
    print(f"{'=' * 50}")
    for r in rounds:
        mark = ' << 采用' if r == rounds[-1] or r['count'] >= target_count else ''
        print(f"  第{r['round']}轮: {r['desc']} → {r['count']}只{mark}")

    print(f"\n  最终候选池: {len(final)} 只")
    if final:
        print(f"  第1名: {final[0]['code']} {final[0]['name']} (评分{final[0]['_score']})")
        print(f"  最后1名: {final[-1]['code']} {final[-1]['name']} (评分{final[-1]['_score']})")
        print(f"  平均ROE: {sum(s['roe'] for s in final)/len(final)*100:.1f}%")
        good_liab = sum(1 for s in final if s['liab_ratio'] < 0.50)
        print(f"  负债<50%: {good_liab}/{len(final)}")

    return final



def fill_names(stocks):
    name_file = os.path.join(DATA_DIR, 'all_stocks.json')
    if not os.path.exists(name_file):
        return stocks
    try:
        with open(name_file, 'r', encoding='utf-8') as f:
            all_s = json.load(f)
        name_map = {s['code']: s['name'] for s in all_s}
        for s in stocks:
            if not s.get('name') and s['code'] in name_map:
                s['name'] = name_map[s['code']]
    except:
        pass
    return stocks

def main():
    parser = argparse.ArgumentParser(description='基本面筛选器：从3030只选出200只候选股')
    parser.add_argument('--roe', type=float, default=7.5, help='最低ROE(%)，默认7.5')
    parser.add_argument('--liab', type=float, default=50, help='最高负债率(%)，默认50')
    parser.add_argument('--gp', type=float, default=20, help='最低毛利率(%)，默认20')
    parser.add_argument('--growth', type=float, default=10, help='最低增长率(%)，默认10')
    parser.add_argument('--count', type=int, default=200, help='目标候选池大小，默认200')
    parser.add_argument('--show', action='store_true', help='只显示不保存')
    args = parser.parse_args()

    print(f"加载基本面数据...")
    stocks_dict = load_fundamentals()
    stocks = fill_names(extract_latest(stocks_dict))
    print(f"  共 {len(stocks_dict)} 只股票，有最新年数据的 {len(stocks)} 只")

    # 筛选
    final = screen(stocks,
                   min_roe=args.roe / 100,
                   max_liab=args.liab / 100,
                   min_gp=args.gp / 100,
                   min_growth=args.growth / 100,
                   target_count=args.count)

    if args.show:
        print(f"\n{'=' * 50}")
        print(f"  候选股列表")
        print(f"{'=' * 50}")
        for i, s in enumerate(final, 1):
            print(f"  {i:3d}. {s['code']} {s['name']:8s}  ROE={s['roe']*100:.1f}%  "
                  f"负债={s['liab_ratio']*100:.0f}%  "
                  f"毛利={s['gp_margin']*100:.0f}%  "
                  f"增长={s['profit_growth']*100:.1f}%  "
                  f"评分={s['_score']}")
        return

    # 保存
    output = {
        'updated': date.today().isoformat(),
        'total': len(final),
        'source': 'screener_fundamentals',
        'criteria': {
            'min_roe_pct': args.roe,
            'max_liab_pct': args.liab,
            'min_gp_pct': args.gp,
            'min_growth_pct': args.growth,
        },
        'candidates': [{
            'code': s['code'],
            'market': s['market'],
            'name': s['name'],
            'roe': s['roe'],
            'liab_ratio': s['liab_ratio'],
            'gp_margin': s['gp_margin'],
            'profit_growth': s['profit_growth'],
            'score': s['_score'],
        } for s in final],
    }

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    file_size = os.path.getsize(OUTPUT_FILE)
    print(f"\n已保存: {OUTPUT_FILE} ({file_size/1024:.0f}KB, {len(final)} 只)")


if __name__ == '__main__':
    main()
