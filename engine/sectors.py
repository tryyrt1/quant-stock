"""板块数据获取与扫描 — 全预定义概念/行业成分股映射"""
import time, json, re, os

PREDEFINED = ["钠电池", "半导体", "电子", "光模块", "CPU", "锂电池", "人工智能", "算力"]

# ─── 预定义板块成分股映射 ───
# 涵盖所有预设板块，不需要外部API(东方财富push2在云服务器不可达)
CONCEPT_MAP = {
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
        except:
            pass
        time.sleep(0.05)

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

    return {
        "sectors": sectors_list,
        "total_sectors": len(sectors_list),
        "total_stocks": len(all_stocks),
        "total_patterns": total_patterns,
    }
