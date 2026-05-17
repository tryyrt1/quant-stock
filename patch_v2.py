"""全功能集成补丁 v2：Baostock数据源 + 排雷 + 技术深度分析"""
import os, re, py_compile

path = "/home/ubuntu/quant-stock/server.py"
with open(path, "r", encoding="utf-8") as f:
    c = f.read()

if "DATA_SOURCE" in c:
    print("already patched v2")
    exit(0)

# ==================== 1. 配置区 ====================
cfg_block = '''
# ─── 数据源配置 ───
DATA_SOURCE = "auto"  # auto | tencent | baostock
BAOSTOCK_INSTALLED = False
try:
    import baostock as bs
    bs.login()
    bs.logout()
    BAOSTOCK_INSTALLED = True
except:
    pass

def get_active_data_source():
    """返回当前生效的数据源"""
    if DATA_SOURCE == "baostock" and BAOSTOCK_INSTALLED:
        return "baostock"
    return "tencent"
'''

insert_pos = c.find("UZI_SKILL_DIR = ")
c = c[:insert_pos] + cfg_block + '\n' + c[insert_pos:]

# ==================== 2. 修改 stock_detail 返回数据源 ====================
old_stock_detail_return = '''    return jsonify({
        'code': code,
        'market': market,
        'quote': quote,
        'kline': kline[-60:],  # 最近60条
        'indicators': indicators,
        'factors': factors,
        'sr': sr,
        'news': news_analyzed[:10],
        'sentiment': round(sentiment_score, 2),
    })'''

new_stock_detail_return = '''    return jsonify({
        'code': code,
        'market': market,
        'quote': quote,
        'kline': kline[-60:],  # 最近60条
        'indicators': indicators,
        'factors': factors,
        'sr': sr,
        'news': news_analyzed[:10],
        'sentiment': round(sentiment_score, 2),
        'data_source': get_active_data_source(),
    })'''

c = c.replace(old_stock_detail_return, new_stock_detail_return)

# ==================== 3. 添加数据源切换端点 ====================
ds_ep = '''

@app.route("/api/datasource", methods=["GET", "POST"])
def datasource_switch():
    """切换/查询数据源"""
    global DATA_SOURCE
    if request.method == "POST":
        ds = request.json.get("source", "auto")
        if ds in ("auto", "tencent", "baostock"):
            DATA_SOURCE = ds
    return jsonify({
        "source": DATA_SOURCE,
        "active": get_active_data_source(),
        "baostock_installed": BAOSTOCK_INSTALLED
    })

'''
# 插入在 @app.route('/api/stock/<code>/uzi', methods=['POST']) 之前
insert_pos = c.find("@app.route('/api/stock/<code>/uzi', methods=['POST'])")
c = c[:insert_pos] + ds_ep + c[insert_pos:]

# ==================== 4. 排雷端点（minesweeper） ====================
ms_ep = '''

# ─── 财报排雷 ───
MINESWEEPER_DIR = os.path.expanduser("~/financial-report-minesweeper")

def _run_minesweeper(code, task_id):
    try:
        os.makedirs(UZI_STATIC_DIR, exist_ok=True)
        log_file = os.path.join(UZI_STATIC_DIR, f"{code}_ms.log")
        cmd = ["python3", "scripts/minesweeper_data.py", "--stock-code", code, "--years", "3"]
        with open(log_file, "w", encoding="utf-8") as log:
            proc = subprocess.run(cmd, cwd=MINESWEEPER_DIR, stdout=log, stderr=log, timeout=120)
        # 读取输出
        out_file = os.path.join(MINESWEEPER_DIR, "output", code, "financial_data.json")
        if os.path.exists(out_file):
            with open(out_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            # 保存到 uzi 目录供前端读取
            dest = os.path.join(UZI_STATIC_DIR, f"{code}_minesweeper.json")
            with open(dest, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            with uzi_tasks_lock:
                uzi_tasks[task_id] = {"status": "done", "url": f"/uzi/{code}_minesweeper.json"}
        else:
            with uzi_tasks_lock:
                uzi_tasks[task_id] = {"status": "error", "msg": "排雷数据未生成，需要 Tushare Token"}
    except Exception as e:
        with uzi_tasks_lock:
            uzi_tasks[task_id] = {"status": "error", "msg": str(e)}

@app.route("/api/stock/<code>/minesweeper", methods=["POST"])
def trigger_minesweeper(code):
    task_id = f"ms_{code}_{int(time.time())}"
    with uzi_tasks_lock:
        uzi_tasks[task_id] = {"status": "running"}
    t = threading.Thread(target=_run_minesweeper, args=(code, task_id), daemon=True)
    t.start()
    return jsonify({"task_id": task_id, "status": "running"})

'''

# 插入在 UZI endpoints 之后，@app.route('/api/scan') 之前
insert_pos = c.find("@app.route('/api/scan')")
c = c[:insert_pos] + ms_ep + c[insert_pos:]

# ==================== 5. 更新 index 路由 ====================
# server.py 的 index() 返回 index.html，不需要改

with open(path, "w", encoding="utf-8") as f:
    f.write(c)

py_compile.compile(path, doraise=True)
print("OK - v2 patch applied")
