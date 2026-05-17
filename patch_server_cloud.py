"""Patch server.py with UZI integration code"""
import re, py_compile

path = "/home/ubuntu/quant-stock/server.py"
with open(path, "r", encoding="utf-8") as f:
    c = f.read()

if "UZI_SKILL_DIR" in c:
    print("already patched")
    exit(0)

# add subprocess to imports
c = c.replace(
    "import json, os, socket, re, time, threading",
    "import json, os, socket, re, time, threading, subprocess, shutil"
)

# UZI config
uzi_cfg = """
# --- UZI-Skill 深度分析集成 ---
UZI_SKILL_DIR = os.path.expanduser("~/UZI-Skill")
UZI_SCRIPTS_DIR = os.path.join(UZI_SKILL_DIR, "skills", "deep-analysis", "scripts")
UZI_REPORTS_DIR = os.path.join(UZI_SCRIPTS_DIR, "reports")
UZI_STATIC_DIR = os.path.join(os.path.dirname(__file__), "static", "uzi")
"""
c = c.replace("from engine.patterns import scan_patterns\n", "from engine.patterns import scan_patterns\n" + uzi_cfg)

# UZI endpoints
uzi_ep = """

# --- UZI 深度分析 ---
uzi_tasks = {}
uzi_tasks_lock = threading.Lock()
UZI_PYTHON = "python3"

def _run_uzi_analysis(code, market, task_id):
    try:
        full_code = market + code if market else code
        if not full_code.startswith(("sh", "sz", "SH", "SZ")):
            full_code = "sh" + code
        cmd = [UZI_PYTHON, "run.py", full_code, "--depth", "lite", "--no-browser"]
        proc = subprocess.run(cmd, cwd=UZI_SKILL_DIR, capture_output=True, text=True, timeout=300)
        from datetime import datetime
        date_str = datetime.now().strftime("%Y%m%d")
        report_dir = os.path.join(UZI_REPORTS_DIR, f"{full_code}_{date_str}")
        standalone = os.path.join(report_dir, "full-report-standalone.html")
        if not os.path.exists(standalone):
            import glob
            candidates = glob.glob(os.path.join(UZI_REPORTS_DIR, f"{full_code}_*", "full-report-standalone.html"))
            if candidates:
                standalone = sorted(candidates)[-1]
        if os.path.exists(standalone):
            os.makedirs(UZI_STATIC_DIR, exist_ok=True)
            dest = os.path.join(UZI_STATIC_DIR, f"{code}.html")
            shutil.copy2(standalone, dest)
            with uzi_tasks_lock:
                uzi_tasks[task_id] = {"status": "done", "url": f"/uzi/{code}.html"}
        else:
            with uzi_tasks_lock:
                uzi_tasks[task_id] = {"status": "error", "msg": "报告未生成"}
    except subprocess.TimeoutExpired:
        with uzi_tasks_lock:
            uzi_tasks[task_id] = {"status": "error", "msg": "超时(5min)"}
    except Exception as e:
        with uzi_tasks_lock:
            uzi_tasks[task_id] = {"status": "error", "msg": str(e)}

@app.route("/api/stock/<code>/uzi", methods=["POST"])
def trigger_uzi_analysis(code):
    market = request.args.get("market", "sh")
    task_id = f"{code}_{int(time.time())}"
    with uzi_tasks_lock:
        uzi_tasks[task_id] = {"status": "running"}
    t = threading.Thread(target=_run_uzi_analysis, args=(code, market, task_id), daemon=True)
    t.start()
    return jsonify({"task_id": task_id, "status": "running"})

@app.route("/api/stock/<code>/uzi/status")
def uzi_analysis_status(code):
    with uzi_tasks_lock:
        candidates = {k: v for k, v in uzi_tasks.items() if k.startswith(f"{code}_")}
        if not candidates:
            return jsonify({"status": "no_task"})
        latest_id = sorted(candidates.keys())[-1]
        return jsonify({"task_id": latest_id, **candidates[latest_id]})

@app.route("/uzi/<path:filename>")
def serve_uzi_report(filename):
    return send_from_directory(UZI_STATIC_DIR, filename)

"""
c = c.replace("@app.route('/api/scan')", uzi_ep + "@app.route('/api/scan')")

with open(path, "w", encoding="utf-8") as f:
    f.write(c)

py_compile.compile(path, doraise=True)
print("OK - patch applied")
