"""板块数据获取与扫描 — 全预定义概念/行业成分股映射 + 异动板块检测"""
import time, json, re, os, concurrent.futures

PREDEFINED = [
    "钠电池", "半导体", "电子", "光模块", "CPU", "锂电池", "人工智能", "算力",
    "有色金属", "白酒", "电力", "银行", "证券", "保险", "煤炭", "钢铁",
    "房地产", "汽车", "新能源汽车", "光伏", "风电", "军工", "医药", "消费电子",
    "AI应用", "家电", "食品饮料", "中字头", "储能", "机器人",
]

# akshare 缓存（备用）
_BOARDS_CACHE = {"time": 0, "data": []}
# 新闻缓存
_NEWS_CACHE = {}

# ─── 预定义板块成分股映射（30+ 热门板块，不需外部API）───
# 每个板块至少 5 只成分股，覆盖常见行业+概念
CONCEPT_MAP = {
    # ── 原有 8 个 ──
    "钠电池": [
        ("600348", "sh", "华阳股份"), ("002455", "sz", "百川股份"),
        ("300174", "sz", "元力股份"), ("002805", "sz", "丰元股份"),
        ("600338", "sh", "西藏珠峰"),
    ],
    "锂电池": [
        ("300750", "sz", "宁德时代"), ("002594", "sz", "比亚迪"),
        ("002074", "sz", "国轩高科"), ("300014", "sz", "亿纬锂能"),
        ("002460", "sz", "赣锋锂业"), ("002466", "sz", "天齐锂业"),
        ("600884", "sh", "杉杉股份"),
    ],
    "光模块": [
        ("300308", "sz", "中际旭创"), ("300502", "sz", "新易盛"),
        ("300394", "sz", "天孚通信"), ("002281", "sz", "光迅科技"),
        ("688313", "sh", "仕佳光子"), ("300548", "sz", "博创科技"),
    ],
    "CPU": [
        ("603986", "sh", "兆易创新"), ("688041", "sh", "海光信息"),
        ("002049", "sz", "紫光国微"), ("300672", "sz", "国科微"),
        ("300458", "sz", "全志科技"), ("688008", "sh", "澜起科技"),
    ],
    "人工智能": [
        ("603019", "sh", "中科曙光"), ("002230", "sz", "科大讯飞"),
        ("300418", "sz", "昆仑万维"), ("688111", "sh", "金山办公"),
        ("000977", "sz", "浪潮信息"), ("002602", "sz", "世纪华通"),
    ],
    "算力": [
        ("603019", "sh", "中科曙光"), ("688041", "sh", "海光信息"),
        ("000977", "sz", "浪潮信息"), ("300308", "sz", "中际旭创"),
        ("688111", "sh", "金山办公"),
    ],
    "半导体": [
        ("002371", "sz", "北方华创"), ("688981", "sh", "中芯国际"),
        ("603501", "sh", "韦尔股份"), ("603986", "sh", "兆易创新"),
        ("002049", "sz", "紫光国微"), ("300782", "sz", "卓胜微"),
        ("300661", "sz", "圣邦股份"), ("600584", "sh", "长电科技"),
        ("688012", "sh", "中微公司"), ("301269", "sz", "华大九天"),
    ],
    "电子": [
        ("002475", "sz", "立讯精密"), ("000725", "sz", "京东方A"),
        ("002415", "sz", "海康威视"), ("002241", "sz", "歌尔股份"),
        ("600703", "sh", "三安光电"), ("002236", "sz", "大华股份"),
        ("300433", "sz", "蓝思科技"), ("600745", "sh", "闻泰科技"),
        ("603160", "sh", "汇顶科技"), ("002456", "sz", "欧菲光"),
    ],
    # ── 新增热门行业板块 ──
    "白酒": [
        ("600519", "sh", "贵州茅台"), ("000858", "sz", "五粮液"),
        ("600809", "sh", "山西汾酒"), ("000568", "sz", "泸州老窖"),
        ("002304", "sz", "洋河股份"), ("600559", "sh", "老白干酒"),
        ("603369", "sh", "今世缘"),
    ],
    "银行": [
        ("601398", "sh", "工商银行"), ("601939", "sh", "建设银行"),
        ("601288", "sh", "农业银行"), ("601328", "sh", "交通银行"),
        ("600036", "sh", "招商银行"), ("601166", "sh", "兴业银行"),
        ("000001", "sz", "平安银行"),
    ],
    "证券": [
        ("600030", "sh", "中信证券"), ("601688", "sh", "华泰证券"),
        ("600837", "sh", "海通证券"), ("000776", "sz", "广发证券"),
        ("601211", "sh", "国泰君安"), ("002736", "sz", "国信证券"),
        ("601878", "sh", "浙商证券"),
    ],
    "保险": [
        ("601318", "sh", "中国平安"), ("601628", "sh", "中国人寿"),
        ("601601", "sh", "中国太保"), ("601336", "sh", "新华保险"),
        ("601319", "sh", "中国人保"),
    ],
    "医药": [
        ("600276", "sh", "恒瑞医药"), ("000538", "sz", "云南白药"),
        ("600196", "sh", "复星医药"), ("300015", "sz", "爱尔眼科"),
        ("600085", "sh", "同仁堂"), ("000423", "sz", "东阿阿胶"),
        ("002007", "sz", "华兰生物"),
    ],
    "汽车": [
        ("600104", "sh", "上汽集团"), ("000625", "sz", "长安汽车"),
        ("002594", "sz", "比亚迪"), ("601238", "sh", "广汽集团"),
        ("600733", "sh", "北汽蓝谷"), ("000800", "sz", "一汽解放"),
    ],
    "地产": [
        ("600048", "sh", "保利发展"), ("000002", "sz", "万科A"),
        ("600383", "sh", "金地集团"), ("001979", "sz", "招商蛇口"),
        ("600606", "sh", "绿地控股"), ("600325", "sh", "华发股份"),
    ],
    "煤炭": [
        ("601088", "sh", "中国神华"), ("601225", "sh", "陕西煤业"),
        ("600188", "sh", "兖矿能源"), ("600985", "sh", "淮北矿业"),
        ("000983", "sz", "山西焦煤"), ("600546", "sh", "山煤国际"),
    ],
    "钢铁": [
        ("600019", "sh", "宝钢股份"), ("000932", "sz", "华菱钢铁"),
        ("600808", "sh", "马钢股份"), ("600282", "sh", "南钢股份"),
        ("000708", "sz", "中信特钢"), ("600010", "sh", "包钢股份"),
    ],
    "有色金属": [
        ("601899", "sh", "紫金矿业"), ("600547", "sh", "山东黄金"),
        ("000975", "sz", "银泰黄金"), ("600489", "sh", "中金黄金"),
        ("603993", "sh", "洛阳钼业"), ("000630", "sz", "铜陵有色"),
    ],
    "电力": [
        ("600900", "sh", "长江电力"), ("600886", "sh", "国投电力"),
        ("600025", "sh", "华能水电"), ("600011", "sh", "华能国际"),
        ("601985", "sh", "中国核电"), ("600905", "sh", "三峡能源"),
    ],
    "通信": [
        ("600941", "sh", "中国移动"), ("600050", "sh", "中国联通"),
        ("601728", "sh", "中国电信"), ("000063", "sz", "中兴通讯"),
        ("600498", "sh", "烽火通信"), ("300502", "sz", "新易盛"),
    ],
    "国防军工": [
        ("600760", "sh", "中航沈飞"), ("600893", "sh", "航发动力"),
        ("600150", "sh", "中国船舶"), ("600685", "sh", "中船防务"),
        ("002625", "sz", "光启技术"), ("600879", "sh", "航天电子"),
    ],
    "光伏": [
        ("601012", "sh", "隆基绿能"), ("600438", "sh", "通威股份"),
        ("688599", "sh", "天合光能"), ("002459", "sz", "晶澳科技"),
        ("600089", "sh", "特变电工"), ("605117", "sh", "德业股份"),
    ],
    "新能源": [
        ("300750", "sz", "宁德时代"), ("002594", "sz", "比亚迪"),
        ("601012", "sh", "隆基绿能"), ("600438", "sh", "通威股份"),
        ("002074", "sz", "国轩高科"), ("300014", "sz", "亿纬锂能"),
        ("002460", "sz", "赣锋锂业"),
    ],
    "白酒消费": [
        ("600519", "sh", "贵州茅台"), ("000858", "sz", "五粮液"),
        ("600887", "sh", "伊利股份"), ("000568", "sz", "泸州老窖"),
        ("600809", "sh", "山西汾酒"), ("600600", "sh", "青岛啤酒"),
        ("603288", "sh", "海天味业"), ("002304", "sz", "洋河股份"),
    ],
    "家电": [
        ("000333", "sz", "美的集团"), ("000651", "sz", "格力电器"),
        ("600690", "sh", "海尔智家"), ("002032", "sz", "苏泊尔"),
        ("002242", "sz", "九阳股份"), ("000100", "sz", "TCL科技"),
    ],
    "化工": [
        ("600309", "sh", "万华化学"), ("601899", "sh", "紫金矿业"),
        ("000830", "sz", "鲁西化工"), ("600352", "sh", "浙江龙盛"),
        ("002601", "sz", "龙佰集团"), ("600426", "sh", "华鲁恒升"),
    ],
    "新能源汽车": [
        ("002594", "sz", "比亚迪"), ("000625", "sz", "长安汽车"),
        ("002460", "sz", "赣锋锂业"), ("002074", "sz", "国轩高科"),
        ("300750", "sz", "宁德时代"), ("002050", "sz", "三花智控"),
        ("600733", "sh", "北汽蓝谷"),
    ],
    "食品饮料": [
        ("600887", "sh", "伊利股份"), ("603288", "sh", "海天味业"),
        ("000895", "sz", "双汇发展"), ("600600", "sh", "青岛啤酒"),
        ("603345", "sh", "安井食品"), ("002568", "sz", "百润股份"),
    ],
    "中字头": [
        ("601857", "sh", "中国石油"), ("600028", "sh", "中国石化"),
        ("601088", "sh", "中国神华"), ("601668", "sh", "中国建筑"),
        ("601390", "sh", "中国中铁"), ("601186", "sh", "中国铁建"),
        ("601800", "sh", "中国交建"), ("600941", "sh", "中国移动"),
    ],
    "基建": [
        ("601668", "sh", "中国建筑"), ("601390", "sh", "中国中铁"),
        ("601186", "sh", "中国铁建"), ("601800", "sh", "中国交建"),
        ("600170", "sh", "上海建工"), ("600502", "sh", "安徽建工"),
    ],
    "航运物流": [
        ("601919", "sh", "中远海控"), ("600026", "sh", "中远海能"),
        ("600428", "sh", "中远海特"), ("601872", "sh", "招商轮船"),
        ("002352", "sz", "顺丰控股"), ("600233", "sh", "圆通速递"),
    ],
    "AI应用": [
        ("002230", "sz", "科大讯飞"), ("300418", "sz", "昆仑万维"),
        ("688111", "sh", "金山办公"), ("002602", "sz", "世纪华通"),
        ("300624", "sz", "万兴科技"), ("002777", "sz", "久远银海"),
    ],
}


def calc_sector_heat(sector_data):
    """计算板块热度指数 (0-100)
    sector_data: {stock_count, up_count, down_count, pattern_count, stocks: [{change_pct}]}
    返回: {heat, heat_signal, prediction}
    """
    total = sector_data["up_count"] + sector_data["down_count"]
    up_ratio = sector_data["up_count"] / total if total > 0 else 0.5
    pat_density = sector_data["pattern_count"] / sector_data["stock_count"] if sector_data["stock_count"] > 0 else 0

    stocks = sector_data.get("stocks", [])
    avg_abs_chg = sum(abs(s.get("change_pct", 0)) for s in stocks) / len(stocks) if stocks else 0

    heat = up_ratio * 40 + min(pat_density, 1) * 30 + min(avg_abs_chg / 5, 1) * 30

    if heat >= 70:
        signal = "🔥 异动上涨"
        prediction = "技术面强势，多只成分股出现突破形态，短期大概率延续上涨"
    elif heat >= 55:
        signal = "📈 活跃"
        prediction = "板块活跃有资金关注，关注后续持续性，可逢低参与"
    elif heat >= 40:
        signal = "➡️ 正常"
        prediction = "板块随大盘波动，方向不明，观望为宜"
    elif heat >= 25:
        signal = "📉 偏弱"
        prediction = "板块承压，缺乏资金关注，等待企稳信号"
    else:
        signal = "⚠️ 弱势"
        prediction = "板块整体弱势，建议回避"

    return {
        "heat": round(heat, 1),
        "heat_signal": signal,
        "prediction": prediction,
        "up_ratio": round(up_ratio * 100, 1),
        "pattern_density": round(pat_density * 100, 1),
    }


def fetch_sector_news(stocks, max_stocks=3):
    """获取板块内成分股新闻，聚合情感
    返回: {sentiment, news_count, news_signal} 或 None
    """
    try:
        from engine.news import fetch_news, analyze_sentiment
        all_news = []
        for stk in stocks[:max_stocks]:
            cache_key = f"{stk['market']}_{stk['code']}"
            if cache_key in _NEWS_CACHE:
                news = _NEWS_CACHE[cache_key]
            else:
                news = fetch_news(stk["code"], stk["market"])
                _NEWS_CACHE[cache_key] = news
            if news:
                all_news.extend(news)

        if not all_news:
            return None

        sentiment, analyzed = analyze_sentiment(all_news)
        if sentiment > 0.2:
            signal = "近期利好居多，市场情绪积极"
        elif sentiment < -0.2:
            signal = "近期偏空消息较多，注意风险"
        else:
            signal = "消息面相对平静"

        return {
            "sentiment": round(sentiment, 2),
            "news_count": len(all_news),
            "news_signal": signal,
        }
    except:
        return None


def fetch_all_boards():
    """从 akshare 获取全市场概念+行业板块列表，计算热度
    返回 [{name, code, type, stock_count, up_count, down_count, change_pct, volume, heat, heat_signal}]
    缓存 1 小时，akshare 不可用时返回空列表
    """
    now = time.time()
    if now - _BOARDS_CACHE["time"] < 3600 and _BOARDS_CACHE["data"]:
        return _BOARDS_CACHE["data"]

    try:
        import akshare as ak
        import pandas as pd

        all_boards = []

        # 概念板块
        try:
            df_concept = ak.stock_board_concept_name_em()
            if df_concept is not None and not df_concept.empty:
                for _, row in df_concept.iterrows():
                    try:
                        up = int(row.get("上涨家数", 0) or 0)
                        down = int(row.get("下跌家数", 0) or 0)
                        total = up + down
                        up_ratio = up / total if total > 0 else 0.5
                        chg = float(row.get("涨跌幅", 0) or 0)
                        vol = float(row.get("成交量", 0) or 0)
                        heat = up_ratio * 40 + min(abs(chg) / 5, 1) * 30 + min(vol / 1e8, 1) * 30
                        all_boards.append({
                            "name": str(row.get("板块名称", "")),
                            "code": str(row.get("板块代码", "")),
                            "type": "concept",
                            "stock_count": total,
                            "up_count": up,
                            "down_count": down,
                            "change_pct": round(chg, 2),
                            "volume": vol,
                            "heat": round(heat, 1),
                        })
                    except Exception as e:
                        print(f'[sectors] 概念板块股票解析失败: {e}')
        except Exception as e:
            print(f'[sectors] akshare概念板块获取失败: {e}')

        # 行业板块
        try:
            df_industry = ak.stock_board_industry_name_em()
            if df_industry is not None and not df_industry.empty:
                for _, row in df_industry.iterrows():
                    try:
                        up = int(row.get("上涨家数", 0) or 0)
                        down = int(row.get("下跌家数", 0) or 0)
                        total = up + down
                        up_ratio = up / total if total > 0 else 0.5
                        chg = float(row.get("涨跌幅", 0) or 0)
                        vol = float(row.get("成交量", 0) or 0)
                        heat = up_ratio * 40 + min(abs(chg) / 5, 1) * 30 + min(vol / 1e8, 1) * 30
                        all_boards.append({
                            "name": str(row.get("板块名称", "")),
                            "code": str(row.get("板块代码", "")),
                            "type": "industry",
                            "stock_count": total,
                            "up_count": up,
                            "down_count": down,
                            "change_pct": round(chg, 2),
                            "volume": vol,
                            "heat": round(heat, 1),
                        })
                    except:
                        pass
        except:
            pass

        # 按热度排序
        all_boards.sort(key=lambda x: -x["heat"])

        # 添加 heat_signal 标签
        for b in all_boards:
            if b["heat"] >= 70:
                b["heat_signal"] = "🔥 异动上涨"
            elif b["heat"] >= 55:
                b["heat_signal"] = "📈 活跃"
            elif b["heat"] >= 40:
                b["heat_signal"] = "➡️ 正常"
            elif b["heat"] >= 25:
                b["heat_signal"] = "📉 偏弱"
            else:
                b["heat_signal"] = "⚠️ 弱势"

        _BOARDS_CACHE["data"] = all_boards
        _BOARDS_CACHE["time"] = now
        return all_boards

    except Exception as e:
        print(f"[sectors] fetch_all_boards error: {e}")
        return []


def fetch_hot_boards(fetch_kline_func, top_n=30, max_stocks=15):
    """取全市场最热的 N 个板块，基于 CONCEPT_MAP + Tencent 实时行情
    两步筛选: 先用涨跌比初筛 top_n*2，再拉 K 线做形态识别精算
    返回 {sectors: [...], total_sectors, total_stocks, total_patterns}
    """
    from engine.patterns import scan_patterns

    if not CONCEPT_MAP:
        return {"sectors": [], "total_sectors": 0, "total_stocks": 0, "total_patterns": 0}

    # ── Step 1: 全量板块 Tencent 批量行情初筛 ──
    all_stock_list = []
    seen_codes = set()
    for name, stocks in CONCEPT_MAP.items():
        for code, market, cname in stocks:
            key = f"{market}_{code}"
            if key not in seen_codes:
                seen_codes.add(key)
                all_stock_list.append({"code": code, "market": market, "name": cname})

    quote_map = {}
    codes_str = ",".join(f"{s['market']}{s['code']}" for s in all_stock_list)
    try:
        import requests as req
        r = req.get(f"https://qt.gtimg.cn/q={codes_str}", timeout=8,
                    headers={"User-Agent": "Mozilla/5.0"})
        r.encoding = "gbk"
        for line in r.text.split(";"):
            if "=" not in line:
                continue
            m = re.search(r'="(.+)"', line)
            if not m:
                continue
            f = m.group(1).split("~")
            if len(f) < 4:
                continue
            code = f[2]
            market = "sh" if code.startswith("6") else "sz"
            price = float(f[3]) if f[3] else 0
            change = float(f[32]) if len(f) > 32 and f[32] else 0
            quote_map[market + code] = {"price": price, "change_pct": round(change, 2)}
    except Exception as e:
        print(f'[sectors] Step1 批量行情失败: {e}')

    # 初步热度（只用 up_ratio + avg_abs_change，不含 pattern）
    sector_prelim = []
    for name, stocks in CONCEPT_MAP.items():
        sector_stocks = []
        up_count = 0
        down_count = 0
        for code, market, cname in stocks:
            q = quote_map.get(market + code, {"price": 0, "change_pct": 0})
            sector_stocks.append({
                "code": code, "market": market, "name": cname,
                "price": q["price"], "change_pct": q["change_pct"],
                "patterns": [],
            })
            if q["change_pct"] >= 0:
                up_count += 1
            else:
                down_count += 1

        total = up_count + down_count
        up_ratio = up_count / total if total > 0 else 0.5
        avg_abs_chg = sum(abs(s["change_pct"]) for s in sector_stocks) / len(sector_stocks) if sector_stocks else 0
        prelim_heat = up_ratio * 40 + min(avg_abs_chg / 5, 1) * 30

        sector_prelim.append({
            "name": name, "stocks": sector_stocks,
            "stock_count": len(sector_stocks),
            "up_count": up_count, "down_count": down_count,
            "prelim_heat": prelim_heat,
        })

    sector_prelim.sort(key=lambda x: -x["prelim_heat"])
    # Step 2 候选：取全部板块，确保有足够的数量到 30
    candidates = sector_prelim[:min(len(sector_prelim), max(60, top_n * 2))]

    # ── Step 2: 精筛 — 拉 K 线做形态识别 ──
    klines_all = {}
    for sd in candidates:
        for stk in sd["stocks"]:
            full_code = stk["market"] + stk["code"]
            if full_code in klines_all:
                continue
            try:
                kline = fetch_kline_func(full_code, 120)
                if kline and len(kline) >= 20:
                    klines_all[full_code] = kline
            except Exception as e:
                print(f'[sectors] {full_code} K线获取失败: {e}')

    pattern_results = scan_patterns(klines_all) if klines_all else {}

    total_patterns = 0
    sectors_data = {}

    for sd in candidates:
        sc = f"sector_{sd['name']}"
        for stk in sd["stocks"]:
            full_code = stk["market"] + stk["code"]
            stk["patterns"] = pattern_results.get(full_code, [])

        pattern_count = sum(1 for stk in sd["stocks"] if stk["patterns"])
        total_patterns += sum(len(stk["patterns"]) for stk in sd["stocks"])

        # 平均涨跌幅
        chg_pcts = [stk["change_pct"] for stk in sd["stocks"]]
        avg_chg = sum(chg_pcts) / len(chg_pcts) if chg_pcts else 0

        sectors_data[sc] = {
            "code": sc, "name": sd["name"], "type": "hot_concept",
            "stock_count": sd["stock_count"],
            "up_count": sd["up_count"], "down_count": sd["down_count"],
            "pattern_count": pattern_count,
            "change_pct": round(avg_chg, 2),
            "stocks": sd["stocks"],
        }

    # 计算热度 + 新闻
    for sd in sectors_data.values():
        heat_info = calc_sector_heat(sd)
        sd.update(heat_info)
        if heat_info["heat"] >= 55:
            news = fetch_sector_news(sd["stocks"], max_stocks=2)
            if news:
                sd["news_sentiment"] = news["sentiment"]
                sd["news_count"] = news["news_count"]
                sd["news_signal"] = news["news_signal"]

    sectors_list = sorted(sectors_data.values(), key=lambda x: -x["heat"])[:top_n]


    final_sectors = []
    for i, sd in enumerate(sectors_list):
        sd["heat_rank"] = i + 1
        final_sectors.append(sd)

    return {
        "sectors": final_sectors,
        "total_sectors": len(final_sectors),
        "total_stocks": sum(sd.get("stock_count", 0) for sd in final_sectors if sd.get("stock_count")),
        "total_patterns": sum(sd.get("pattern_count", 0) for sd in final_sectors),
    }


def _get_stock_market(code):
    if code.startswith("6") or code.startswith("9") or code.startswith("688"):
        return "sh"
    return "sz"


def search_sectors(names, board_type="both"):
    """按名称匹配板块（全预定义映射，无需外部API）
    返回 [{display_name, sector_code, sector_name, stock_count, found, type}]
    """
    result = []
    for name in names:
        if name in CONCEPT_MAP:
            stocks = CONCEPT_MAP[name]
            result.append({
                "display_name": name,
                "sector_code": f"sector_{name}",
                "sector_name": name,
                "stock_count": len(stocks),
                "found": True,
                "type": "concept",
            })
        else:
            result.append({
                "display_name": name,
                "sector_code": None,
                "sector_name": None,
                "stock_count": 0,
                "found": False,
                "type": None,
            })
    return result


def get_sector_stocks(sector_code, max_stocks=30):
    """获取板块成分股"""
    if sector_code.startswith("sector_"):
        name = sector_code[7:]
        if name in CONCEPT_MAP:
            raw = CONCEPT_MAP[name]
            return [{
                "code": c, "market": m, "name": n,
                "price": 0, "change_pct": 0,
            } for c, m, n in raw]
    return []


def scan_sector_stocks(sector_codes, fetch_kline_func, max_stocks=30, kline_days=120):
    """扫描多个板块，对成分股做形态识别
    返回 {sectors: [...], total_sectors, total_stocks, total_patterns}
    """
    from engine.patterns import scan_patterns

    all_stocks = []
    seen = set()
    sector_info_map = {}

    for sc in sector_codes:
        stocks = get_sector_stocks(sc, max_stocks)
        if sc.startswith("sector_"):
            sector_info_map[sc] = {"code": sc, "name": sc[7:], "type": "concept"}
        else:
            sector_info_map[sc] = {"code": sc, "name": sc, "type": ""}

        for stk in stocks:
            dedup_key = f"{stk['market']}_{stk['code']}"
            if dedup_key not in seen:
                seen.add(dedup_key)
                stk["sector_codes"] = [sc]
                all_stocks.append(stk)
            else:
                for existing in all_stocks:
                    if existing["market"] == stk["market"] and existing["code"] == stk["code"]:
                        existing["sector_codes"].append(sc)
                        break

    # 获取K线
    klines_all = {}
    for stk in all_stocks:
        full_code = stk["market"] + stk["code"]
        try:
            kline = fetch_kline_func(full_code, kline_days)
            if kline and len(kline) >= 20:
                klines_all[full_code] = kline
        except Exception as e:
            print(f'[sectors] {full_code} K线获取失败: {e}')
        time.sleep(0.02)

    # 获取实时行情
    if all_stocks:
        codes_str = ",".join(f"{s['market']}{s['code']}" for s in all_stocks)
        try:
            import requests as req
            r = req.get(f"https://qt.gtimg.cn/q={codes_str}", timeout=8,
                        headers={"User-Agent": "Mozilla/5.0"})
            r.encoding = "gbk"
            for line in r.text.split(";"):
                if "=" not in line:
                    continue
                m = re.search(r'="(.+)"', line)
                if not m:
                    continue
                f = m.group(1).split("~")
                if len(f) < 4:
                    continue
                code = f[2]
                price = float(f[3]) if f[3] else 0
                change = float(f[32]) if len(f) > 32 and f[32] else 0
                for stk in all_stocks:
                    if stk["code"] == code:
                        stk["price"] = price
                        stk["change_pct"] = round(change, 2)
                        break
        except:
            pass

    # 形态扫描
    pattern_results = scan_patterns(klines_all) if klines_all else {}

    total_patterns = 0
    sectors_data = {}

    for stk in all_stocks:
        full_code = stk["market"] + stk["code"]
        patterns = pattern_results.get(full_code, [])
        has_pat = len(patterns) > 0
        if has_pat:
            total_patterns += len(patterns)

        for sc in stk.get("sector_codes", []):
            if sc not in sectors_data:
                si = sector_info_map.get(sc, {})
                sectors_data[sc] = {
                    "code": sc,
                    "name": si.get("name", sc),
                    "type": si.get("type", ""),
                    "stock_count": 0,
                    "up_count": 0,
                    "down_count": 0,
                    "pattern_count": 0,
                    "stocks": [],
                }
            sd = sectors_data[sc]
            sd["stock_count"] += 1
            if stk.get("change_pct", 0) >= 0:
                sd["up_count"] += 1
            else:
                sd["down_count"] += 1
            if has_pat:
                sd["pattern_count"] += 1
            sd["stocks"].append({
                "code": stk["code"],
                "market": stk["market"],
                "name": stk["name"],
                "price": stk.get("price", 0),
                "change_pct": stk.get("change_pct", 0),
                "patterns": patterns,
            })

    sectors_list = sorted(sectors_data.values(), key=lambda x: -x["pattern_count"])

    # 计算热度 + 新闻
    for sd in sectors_list:
        heat_info = calc_sector_heat(sd)
        sd.update(heat_info)
        if heat_info["heat"] >= 55:
            news = fetch_sector_news(sd["stocks"], max_stocks=3)
            if news:
                sd["news_sentiment"] = news["sentiment"]
                sd["news_count"] = news["news_count"]
                sd["news_signal"] = news["news_signal"]

    # 按热度排序
    sectors_list.sort(key=lambda x: -x["heat"])

    return {
        "sectors": sectors_list,
        "total_sectors": len(sectors_list),
        "total_stocks": len(all_stocks),
        "total_patterns": total_patterns,
    }
