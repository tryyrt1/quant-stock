"""
主升浪前20日量价规律分析
=======================
用 Tushare 找出最近120个交易日中符合条件的股票（非创业板/非科创板/非ST/非亏损），
筛选出曾有一波拉升 ≥100% 的主升浪，分析主升浪前20日的量价与K线规律。

分两阶段：
1. fetch: 拉数据 + 筛选候选 → 写入 data/surge_candidates.txt，等用户确认
2. analyze: 分析候选池 → 输出 data/surge_analysis_results.json + report.md

用法:
    python analyze_surge.py fetch      # 第一步：获取数据并输出候选列表
    python analyze_surge.py analyze     # 第二步：分析候选池
"""

import os, sys, json, time
from datetime import datetime, timedelta

import pandas as pd
import numpy as np

# ==== 配置 ====
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
CANDIDATES_FILE = os.path.join(OUTPUT_DIR, 'surge_candidates.txt')
RESULTS_FILE = os.path.join(OUTPUT_DIR, 'surge_analysis_results.json')
REPORT_FILE = os.path.join(OUTPUT_DIR, 'surge_analysis_report.md')
TRADE_DAYS = 120           # 考察区间
MIN_SURGE_PCT = 100        # 最小拉升幅度 %
MIN_SURGE_DAYS = 5         # 拉升最短持续天数（交易日）
PRE_SURGE_WINDOW = 20      # 主升浪前取多少个交易日
FETCH_BATCH_SIZE = 5       # 每次批量请求的交易日数（合并请求减少 API 调用）

# 排除的板块前缀
EXCLUDE_PREFIXES = ('300', '688')
EXCLUDE_KEYWORDS = ('ST', '退', 'N')  # *ST handled separately

def _log(msg):
    print(f"  [{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

# ==== Tushare 初始化 ====

def init_tushare():
    token = os.environ.get('TUSHARE_TOKEN', '')
    if not token:
        # 回退：从 .tushare_token 文件读取
        tf = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.tushare_token')
        if os.path.exists(tf):
            with open(tf) as f:
                token = f.read().strip()
    if not token:
        print("错误: TUSHARE_TOKEN 环境变量未设置")
        sys.exit(1)
    import tushare as ts
    ts.set_token(token)
    pro = ts.pro_api()
    _log(f"Tushare 已连接 (Token: {token[:8]}...)")
    return pro


# ==== Step 1: 获取股票基础信息 ====

def fetch_stock_basic(pro):
    """获取全部A股基础信息，排除创业板/科创板/ST"""
    _log("拉取 stock_basic...")
    df = pro.stock_basic(
        fields='ts_code,symbol,name,market,list_status,is_hs'
    )
    if df is None or len(df) == 0:
        print("错误: stock_basic 返回空")
        sys.exit(1)
    _log(f"  stock_basic: {len(df)} 只")

    # 筛选：上市状态正常、非创业板、非科创板、非ST
    before = len(df)
    df = df[df['list_status'] == 'L']  # L=上市

    # 排除代码前缀
    mask = ~df['symbol'].str.startswith('300')
    mask &= ~df['symbol'].str.startswith('688')
    # 排除名称含 ST / *ST / 退
    for kw in EXCLUDE_KEYWORDS:
        mask &= ~df['name'].str.contains(kw, na=False, regex=False)
    # *ST is a regex pattern, handle separately
    mask &= ~df['name'].str.contains(r'\*ST', na=False, regex=True)
    df = df[mask]
    _log(f"  排除后: {len(df)} 只 (排除 {before - len(df)} 只)")

    return df[['symbol', 'name']].copy()


# ==== Step 2: 按交易日批量拉取日线 + daily_basic(PE) ====

def fetch_trade_cal(pro, days=TRADE_DAYS):
    """获取最近 N 个交易日列表"""
    end_date = datetime.now().strftime('%Y%m%d')
    start = datetime.now() - timedelta(days=days * 2)  # 留余量
    start_date = start.strftime('%Y%m%d')
    _log(f"拉取交易日历 {start_date} ~ {end_date}...")
    df = pro.trade_cal(start_date=start_date, end_date=end_date)
    if df is None or len(df) == 0:
        print("错误: trade_cal 返回空")
        sys.exit(1)
    # 筛选交易日 + 最近的 N 天
    df = df[df['is_open'] == 1].tail(days)
    trade_dates = df['cal_date'].tolist()
    _log(f"  共 {len(trade_dates)} 个交易日")
    return trade_dates


def fetch_daily_and_basic(pro, trade_date):
    """获取一天的日线 + daily_basic(含PE)"""
    df_daily = pro.daily(trade_date=trade_date,
                         fields='ts_code,trade_date,open,high,low,close,vol,amount,pct_chg')
    df_basic = pro.daily_basic(trade_date=trade_date,
                               fields='ts_code,pe,pe_ttm,turnover_rate')
    if df_daily is not None and df_basic is not None:
        # 合并
        df = df_daily.merge(df_basic, on='ts_code', how='left')
        return df
    elif df_daily is not None:
        return df_daily
    return None


def fetch_all_data(pro, trade_dates, stock_basic_df):
    """遍历交易日拉取全市场数据"""
    all_dfs = []
    total = len(trade_dates)

    # stock_basic 映射: symbol + market → ts_code
    # Tushare daily 返回 ts_code 如 '000001.SZ'
    # 我们只需要 symbol 做过滤，先建一个 symbol_set
    valid_symbols = set(stock_basic_df['symbol'].tolist())

    for i, date in enumerate(trade_dates):
        _log(f"拉取 [{i+1}/{total}] {date}...")
        df = fetch_daily_and_basic(pro, date)
        if df is not None and len(df) > 0:
            # 提取 symbol（去掉.SZ/.SH后缀）
            df['symbol'] = df['ts_code'].str.split('.').str[0]
            # 只保留有效股票
            df = df[df['symbol'].isin(valid_symbols)]
            if len(df) > 0:
                all_dfs.append(df)
        # 限速休息 — Tushare 限频 200/min，我们实际约 15-20 calls/min
        time.sleep(0.3)

    if not all_dfs:
        print("错误: 未能获取任何日线数据")
        sys.exit(1)

    result = pd.concat(all_dfs, ignore_index=True)
    _log(f"全量数据: {len(result)} 行, {result['symbol'].nunique()} 只股票")
    return result


# ==== Step 3: 筛选剔除亏损股 ====

def filter_loss_making(df):
    """剔除过去区间内任意 PE ≤ 0 的股票"""
    if 'pe' not in df.columns:
        _log("警告: 无 PE 数据，跳过亏损筛选")
        return df

    _log("筛除亏损股(PE≤0)...")
    before = df['symbol'].nunique()
    # 标记每只股票是否有 PE ≤ 0 记录
    bad = df.groupby('symbol')['pe'].apply(lambda x: (x <= 0).any())
    bad_symbols = set(bad[bad].index)
    # 也筛掉 PE 全为空的
    all_null = df.groupby('symbol')['pe'].apply(lambda x: x.isna().all())
    all_null_symbols = set(all_null[all_null].index)
    exclude = bad_symbols | all_null_symbols

    df = df[~df['symbol'].isin(exclude)]
    after = df['symbol'].nunique()
    _log(f"  排除 {before - after} 只亏损/无PE股, 剩余 {after} 只")
    return df


# ==== Step 4: 输出候选股票列表 ====

def write_candidates(df, stock_basic_df):
    """写入候选股票列表到文本文件"""
    symbols = sorted(df['symbol'].unique())
    # 建立 symbol → name 映射
    name_map = dict(zip(stock_basic_df['symbol'], stock_basic_df['name']))

    lines = [f"# 候选股票列表 ({len(symbols)} 只)", "# 生成时间: " + datetime.now().strftime('%Y-%m-%d %H:%M')]
    lines.append("# 筛选条件: [上市] + [非创业板/科创板/ST/亏损] + 有120日交易数据")
    lines.append("# 格式: 代码 名称")
    lines.append("")
    for sym in symbols:
        name = name_map.get(sym, '')
        lines.append(f"{sym} {name}")

    with open(CANDIDATES_FILE, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')

    _log(f"候选列表已写入: {CANDIDATES_FILE}")
    # 打印前 20 只
    print(f"\n前 20 只候选股票:")
    for l in lines[4:24]:
        print(f"  {l}")
    print(f"  ... 共 {len(symbols)} 只\n")
    print("=" * 60)
    print(f"✅ Step 1 完成! 候选列表已写入 {CANDIDATES_FILE}")
    print(f"   运行第二步: python analyze_surge.py analyze")
    print("=" * 60)


# ==== Step 5-6: 识别主升浪 + 截取前20日 ====

def find_surges(df, stock_basic_df):
    """对候选池每只股票找主升浪起点"""
    name_map = dict(zip(stock_basic_df['symbol'], stock_basic_df['name']))
    results = []

    symbols = sorted(df['symbol'].unique())
    total = len(symbols)

    for i, sym in enumerate(symbols):
        if (i + 1) % 50 == 0:
            _log(f"分析进度 [{i+1}/{total}]...")

        sdf = df[df['symbol'] == sym].sort_values('trade_date').reset_index(drop=True)
        if len(sdf) < MIN_SURGE_DAYS + PRE_SURGE_WINDOW:
            continue

        closes = sdf['close'].values
        highs = sdf['high'].values
        lows = sdf['low'].values
        vols = sdf['vol'].values
        pct_changes = sdf['pct_chg'].values
        dates = sdf['trade_date'].values

        # 滑动窗口找主升浪
        found_surge = False
        for start in range(len(sdf) - MIN_SURGE_DAYS):
            for end in range(start + MIN_SURGE_DAYS, min(start + 60, len(sdf))):
                # 从 start 到 end 的累计涨幅
                gain = (closes[end] - closes[start]) / closes[start] * 100
                if gain >= MIN_SURGE_PCT:
                    # 找到主升浪
                    if start < PRE_SURGE_WINDOW:
                        continue  # 前20日不够就不纳入

                    # 截取前 PRE_SURGE_WINDOW 日
                    pre_start = start - PRE_SURGE_WINDOW
                    pre_dates = dates[pre_start:start]
                    pre_closes = closes[pre_start:start]
                    pre_highs = highs[pre_start:start]
                    pre_lows = lows[pre_start:start]
                    pre_vols = vols[pre_start:start]
                    pre_pct = pct_changes[pre_start:start]
                    pre_opens = sdf['open'].values[pre_start:start]

                    # 统计
                    pre_gains = []  # 每日涨跌幅
                    pre_amplitudes = []  # 每日振幅
                    vol_ratio_list = []  # 量比（当日量/前5日均量）
                    up_days = 0  # 阳线天数

                    for j in range(PRE_SURGE_WINDOW):
                        daily_gain = (pre_closes[j] - pre_opens[j]) / pre_opens[j] * 100
                        pre_gains.append(daily_gain)
                        amp = (pre_highs[j] - pre_lows[j]) / pre_lows[j] * 100
                        pre_amplitudes.append(amp)
                        if pre_closes[j] >= pre_opens[j]:
                            up_days += 1

                        # 量比（前5日均量对比）
                        if j >= 5:
                            avg5 = np.mean(pre_vols[j-5:j])
                            vol_ratio_list.append(pre_vols[j] / avg5 if avg5 > 0 else 1.0)

                    # 整理统计量
                    stats = {
                        'symbol': sym,
                        'name': name_map.get(sym, ''),
                        'surge_start': str(dates[start]),
                        'surge_end': str(dates[end]),
                        'surge_gain_pct': round(gain, 2),
                        'surge_duration': end - start + 1,
                        'pre_20d_avg_gain': round(np.mean(pre_gains), 2),
                        'pre_20d_avg_amplitude': round(np.mean(pre_amplitudes), 2),
                        'pre_20d_up_ratio': round(up_days / PRE_SURGE_WINDOW, 2),
                        'pre_20d_avg_vol_ratio': round(np.mean(vol_ratio_list), 2) if vol_ratio_list else None,
                        'pre_20d_vol_trend': None,  # 后10日量/前10日量
                        'pre_20d_lowest_close': round(min(pre_closes), 2),
                        'pre_20d_highest_close': round(max(pre_closes), 2),
                        'pre_20d_start_close': round(pre_closes[0], 2),
                        'pre_20d_end_close': round(pre_closes[-1], 2),
                        'pre_20d_gain': round((pre_closes[-1] - pre_closes[0]) / pre_closes[0] * 100, 2),
                        'consecutive_up_days': None,  # 连续阳线天数
                        'consecutive_down_days': None,
                    }

                    # 量趋势：后10日均量 / 前10日均量
                    if PRE_SURGE_WINDOW >= 20:
                        vol_first_half = np.mean(pre_vols[:10])
                        vol_second_half = np.mean(pre_vols[10:])
                        if vol_first_half > 0:
                            stats['pre_20d_vol_trend'] = round(vol_second_half / vol_first_half, 2)

                    # 连续涨/跌天数
                    max_up = max_down = cur_up = cur_down = 0
                    for g in pre_pct:
                        if g > 0:
                            cur_up += 1
                            cur_down = 0
                        else:
                            cur_down += 1
                            cur_up = 0
                        max_up = max(max_up, cur_up)
                        max_down = max(max_down, cur_down)
                    stats['consecutive_up_days'] = max_up
                    stats['consecutive_down_days'] = max_down

                    results.append(stats)
                    found_surge = True
                    break
            if found_surge:
                break

    _log(f"分析完成: {len(results)} 只股票有主升浪记录")
    return results


# ==== Step 7: 输出分析结果 ====

def write_results(results):
    """写入 JSON 结果 + Markdown 报告"""

    # JSON 原始数据
    with open(RESULTS_FILE, 'w', encoding='utf-8') as f:
        json.dump({
            'total_stocks': len(results),
            'generated_at': datetime.now().isoformat(),
            'stocks': results
        }, f, ensure_ascii=False, indent=2)
    _log(f"结果已写入: {RESULTS_FILE}")

    # --- 汇总统计 ---
    df = pd.DataFrame(results)
    report_lines = []
    report_lines.append("# 主升浪前20日量价规律分析报告")
    report_lines.append("")
    report_lines.append(f"**生成时间:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    report_lines.append(f"**考察区间:** 最近 {TRADE_DAYS} 个交易日")
    report_lines.append(f"**符合条件股票:** {len(results)} 只 (拉升 ≥{MIN_SURGE_PCT}%, 持续 ≥{MIN_SURGE_DAYS}天)")
    report_lines.append("")

    if len(results) == 0:
        report_lines.append("**未找到符合条件的股票。**")
        report_lines.append("可能原因：1) 最近 120 日内无股票达到 100%+ 拉升；2) Tushare 数据覆盖不完整。")
        with open(REPORT_FILE, 'w', encoding='utf-8') as f:
            f.write('\n'.join(report_lines))
        return

    report_lines.append("---")
    report_lines.append("## 一、前20日总体统计")
    report_lines.append("")

    numeric_cols = ['pre_20d_avg_gain', 'pre_20d_avg_amplitude', 'pre_20d_up_ratio',
                    'pre_20d_vol_trend', 'pre_20d_gain',
                    'consecutive_up_days', 'consecutive_down_days',
                    'surge_gain_pct', 'surge_duration']
    # 过滤数字列
    available = [c for c in numeric_cols if c in df.columns]
    stats = df[available].describe().round(2)
    report_lines.append("```")
    report_lines.append(stats.to_string())
    report_lines.append("```")
    report_lines.append("")

    # --- 前20日涨跌幅分布 ---
    report_lines.append("### 前20日涨跌幅分布")
    report_lines.append("")
    bins = [-999, -30, -20, -10, -5, 0, 5, 10, 20, 30, 999]
    labels = ['<-30%', '-30~-20%', '-20~-10%', '-10~-5%', '-5~0%',
              '0~5%', '5~10%', '10~20%', '20~30%', '>30%']
    if 'pre_20d_gain' in df.columns:
        df['gain_bucket'] = pd.cut(df['pre_20d_gain'], bins=bins, labels=labels)
        dist = df['gain_bucket'].value_counts().sort_index()
        report_lines.append("| 区间 | 数量 | 占比 |")
        report_lines.append("|------|------|------|")
        for label in labels:
            cnt = dist.get(label, 0)
            pct = cnt / len(df) * 100
            bar = '█' * int(pct / 2)
            report_lines.append(f"| {label} | {cnt} | {pct:.1f}% {bar} |")
    report_lines.append("")

    # --- 阳线比例分布 ---
    report_lines.append("### 前20日阳线比例分布")
    report_lines.append("")
    bins2 = [-1, 0.25, 0.35, 0.45, 0.5, 0.55, 0.65, 0.75, 1.01]
    labels2 = ['<25%', '25-35%', '35-45%', '45-50%', '50-55%', '55-65%', '65-75%', '>75%']
    if 'pre_20d_up_ratio' in df.columns:
        df['up_bucket'] = pd.cut(df['pre_20d_up_ratio'], bins=bins2, labels=labels2)
        dist2 = df['up_bucket'].value_counts().sort_index()
        report_lines.append("| 区间 | 数量 | 占比 |")
        report_lines.append("|------|------|------|")
        for lbl in labels2:
            cnt = dist2.get(lbl, 0)
            pct = cnt / len(df) * 100
            bar = '█' * int(pct / 2)
            report_lines.append(f"| {lbl} | {cnt} | {pct:.1f}% {bar} |")
    report_lines.append("")

    # --- 量趋势分布 ---
    report_lines.append("### 前20日量比趋势（后10日/前10日）")
    report_lines.append("")
    if 'pre_20d_vol_trend' in df.columns:
        vol_valid = df['pre_20d_vol_trend'].dropna()
        avg_vol_ratio = vol_valid.mean()
        vol_up = (vol_valid > 1.0).sum()
        vol_down = (vol_valid <= 1.0).sum()
        report_lines.append(f"- 量比均值: {avg_vol_ratio:.2f}")
        report_lines.append(f"- 后10日放量: {vol_up} 只 ({vol_up/len(vol_valid)*100:.1f}%)")
        report_lines.append(f"- 后10日缩量: {vol_down} 只 ({vol_down/len(vol_valid)*100:.1f}%)")
    report_lines.append("")

    # --- 连续阳线 ---
    report_lines.append("### 前20日连续阳线特征")
    report_lines.append("")
    if 'consecutive_up_days' in df.columns:
        avg_consec_up = df['consecutive_up_days'].mean()
        max_consec_up = df['consecutive_up_days'].max()
        consec_up_3 = (df['consecutive_up_days'] >= 3).sum()
        consec_up_5 = (df['consecutive_up_days'] >= 5).sum()
        report_lines.append(f"- 平均最大连续阳线: {avg_consec_up:.1f} 天")
        report_lines.append(f"- 出现过 ≥3天连阳: {consec_up_3} 只 ({consec_up_3/len(df)*100:.1f}%)")
        report_lines.append(f"- 出现过 ≥5天连阳: {consec_up_5} 只 ({consec_up_5/len(df)*100:.1f}%)")
    report_lines.append("")

    # --- 每只股票详细数据（表格） ---
    report_lines.append("---")
    report_lines.append("## 二、每只股票详细数据")
    report_lines.append("")
    report_lines.append("| 代码 | 名称 | 前20日涨跌幅 | 日均振幅 | 阳线比例 | 均涨幅 | 量比 | 连阳(最大) | 主升浪涨幅 | 天数 |")
    report_lines.append("|------|------|------------|---------|---------|-------|------|-----------|-----------|------|")
    for r in results:
        report_lines.append(
            f"| {r['symbol']} | {r['name']} "
            f"| {r.get('pre_20d_gain', '?')}% "
            f"| {r.get('pre_20d_avg_amplitude', '?')}% "
            f"| {r.get('pre_20d_up_ratio', '?')} "
            f"| {r.get('pre_20d_avg_gain', '?')}% "
            f"| {r.get('pre_20d_vol_trend', '?')} "
            f"| {r.get('consecutive_up_days', '?')} "
            f"| {r.get('surge_gain_pct', '?')}% "
            f"| {r.get('surge_duration', '?')} |"
        )
    report_lines.append("")

    with open(REPORT_FILE, 'w', encoding='utf-8') as f:
        f.write('\n'.join(report_lines))
    _log(f"报告已写入: {REPORT_FILE}")


# ==== 主入口 ====

def main():
    if len(sys.argv) < 2:
        print("用法: python analyze_surge.py fetch    # 第一步：获取数据 + 输出候选列表")
        print("       python analyze_surge.py analyze  # 第二步：分析候选池")
        sys.exit(1)

    mode = sys.argv[1]

    # 确保输出目录
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    if mode == 'fetch':
        pro = init_tushare()

        # Step 1: 股票基础信息
        stock_df = fetch_stock_basic(pro)

        # Step 2: 交易日历
        trade_dates = fetch_trade_cal(pro)
        if not trade_dates:
            sys.exit(1)

        # Step 2b: 拉数据
        df = fetch_all_data(pro, trade_dates, stock_df)

        # 缓存原始数据供第二步使用
        cache_file = os.path.join(OUTPUT_DIR, '_all_daily.pkl')
        df.to_pickle(cache_file)
        stock_df.to_pickle(os.path.join(OUTPUT_DIR, '_stock_basic.pkl'))
        _log(f"原始数据已缓存: {cache_file} ({len(df)} 行)")

        # Step 3: 筛亏损
        df = filter_loss_making(df)

        # Step 4: 写候选列表
        write_candidates(df, stock_df)

    elif mode == 'analyze':
        # 检查候选文件
        if not os.path.exists(CANDIDATES_FILE):
            print(f"错误: 先运行 python analyze_surge.py fetch 生成 {CANDIDATES_FILE}")
            sys.exit(1)

        # 加载缓存数据
        cache_file = os.path.join(OUTPUT_DIR, '_all_daily.pkl')
        stock_cache = os.path.join(OUTPUT_DIR, '_stock_basic.pkl')
        if not os.path.exists(cache_file):
            print(f"错误: 未找到缓存数据 {cache_file}，请先运行 fetch")
            sys.exit(1)

        df = pd.read_pickle(cache_file)
        stock_df = pd.read_pickle(stock_cache)

        # 读取候选列表中的 symbol
        candidates = []
        with open(CANDIDATES_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    parts = line.split()
                    if parts:
                        candidates.append(parts[0])

        _log(f"加载候选池: {len(candidates)} 只股票")
        df = df[df['symbol'].isin(candidates)]

        # Step 5-6: 识别主升浪
        results = find_surges(df, stock_df)

        # Step 7: 输出
        write_results(results)

        print("\n" + "=" * 60)
        print(f"✅ 分析完成!")
        print(f"   JSON: {RESULTS_FILE}")
        print(f"   报告: {REPORT_FILE}")
        print(f"   符合条件: {len(results)} 只")
        print("=" * 60)

    else:
        print(f"未知模式: {mode}")
        sys.exit(1)


if __name__ == '__main__':
    main()
