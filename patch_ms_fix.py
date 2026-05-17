"""Fix minesweeper output reading + add status endpoint"""
path = "/home/ubuntu/quant-stock/server.py"
with open(path, "r", encoding="utf-8") as f:
    c = f.read()

# Fix 1: Replace out_file check with reading from log
old = '''        out_file = os.path.join(MINESWEEPER_DIR, "output", code, "financial_data.json")
        if os.path.exists(out_file):
            with open(out_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            dest = os.path.join(UZI_STATIC_DIR, f"{code}_minesweeper.json")
            with open(dest, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            with uzi_tasks_lock:
                uzi_tasks[task_id] = {"status": "done", "url": f"/uzi/{code}_minesweeper.json"}
        else:
            with uzi_tasks_lock:
                uzi_tasks[task_id] = {"status": "error", "msg": "排雷数据未生成，请检查股票代码是否正确"}'''

new = '''        # Read JSON from log file (baostock script writes JSON to stdout)
        data = None
        with open(log_file, "r", encoding="utf-8") as f:
            content = f.read()
            import re as _re
            m = _re.search(r'\{.*', content, _re.DOTALL)
            if m:
                try:
                    data = json.loads(m.group())
                except:
                    pass
        if data:
            dest = os.path.join(UZI_STATIC_DIR, f"{code}_minesweeper.json")
            with open(dest, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            with uzi_tasks_lock:
                uzi_tasks[task_id] = {"status": "done", "url": f"/uzi/{code}_minesweeper.json"}
        else:
            with uzi_tasks_lock:
                uzi_tasks[task_id] = {"status": "error", "msg": "排雷数据未生成"}'''

c = c.replace(old, new)

# Fix 2: Add minesweeper status endpoint
old2 = '''@app.route('/api/stock/<code>/minesweeper', methods=['POST'])
def trigger_minesweeper(code):'''

status_endpoint = '''
@app.route('/api/stock/<code>/minesweeper/status')
def minesweeper_status(code):
    """查询排雷状态"""
    with uzi_tasks_lock:
        prefix = "ms_" + code + "_"
        candidates = {k: v for k, v in uzi_tasks.items() if k.startswith(prefix)}
        if not candidates:
            return jsonify({'status': 'no_task'})
        latest_id = sorted(candidates.keys())[-1]
        return jsonify({'task_id': latest_id, **candidates[latest_id]})

''' + old2

c = c.replace(old2, status_endpoint)

with open(path, "w", encoding="utf-8") as f:
    f.write(c)

import py_compile
py_compile.compile(path, doraise=True)
print("OK")
