#!/usr/bin/env python3
"""在云服务器 server.py 中插入 UZI-Skill 集成代码"""
import os

SERVER_PY = '/home/ubuntu/quant-stock/server.py'

with open(SERVER_PY, 'r', encoding='utf-8') as f:
    content = f.read()

# 如果已经插入了就跳过
if 'UZI_SKILL_DIR' in content:
    print("✓ UZI 代码已存在，跳过插入")
else:
    # 1. 在 import 行加 subprocess
    content = content.replace(
        'import json, os, socket, re, time, threading',
        'import json, os, socket, re, time, threading, subprocess, shutil'
    )

    # 2. 在文件头加 UZI 路径配置（在 import 后，第一个 @app.route 前）
    uzi_config = '''
# ─── UZI-Skill 深度分析集成 ───
UZI_SKILL_DIR = os.path.expanduser("~/UZI-Skill")
UZI_SCRIPTS_DIR = os.path.join(UZI_SKILL_DIR, 'skills', 'deep-analysis', 'scripts')
UZI_REPORTS_DIR = os.path.join(UZI_SCRIPTS_DIR, 'reports')
UZI_STATIC_DIR = os.path.join(os.path.dirname(__file__), 'static', 'uzi')
'''
    # 插入在 STATIC_STOCKS 定义之前
    insert_pos = content.find('STATIC_STOCKS = [')
    content = content[:insert_pos] + uzi_config + content[insert_pos:]

    # 3. 在 stock_detail endpoint 之后插入 UZI 端点
    uzi_endpoints = '''

# ─── UZI 深度分析任务存储 ───
uzi_tasks = {}
uzi_tasks_lock = threading.Lock()
UZI_PYTHON = 'python3'


def _run_uzi_analysis(code, market, task_id):
    """后台运行 UZI 分析"""
    try:
        full_code = market + code if market else code
        if not full_code.startswith(('sh', 'sz', 'SH', 'SZ')):
            full_code = 'sh' + code

        cmd = [UZI_PYTHON, 'run.py', full_code, '--depth', 'lite', '--no-browser']
        proc = subprocess.run(cmd, cwd=UZI_SKILL_DIR, capture_output=True, text=True, timeout=300)

        # 找到生成的最新报告
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
                uzi_tasks[task_id] = {'status': 'done', 'url': f'/uzi/{code}.html', 'file': dest}
        else:
            log_file = os.path.join(UZI_STATIC_DIR, f"{code}_log.txt")
            with open(log_file, 'w', encoding='utf-8') as f:
                f.write(f"STDOUT:\\n{proc.stdout}\\n\\nSTDERR:\\n{proc.stderr}")
            with uzi_tasks_lock:
                uzi_tasks[task_id] = {'status': 'error', 'msg': '报告未生成'}

    except subprocess.TimeoutExpired:
        with uzi_tasks_lock:
            uzi_tasks[task_id] = {'status': 'error', 'msg': '分析超时(5min)'}
    except Exception as e:
        with uzi_tasks_lock:
            uzi_tasks[task_id] = {'status': 'error', 'msg': str(e)}


@app.route('/api/stock/<code>/uzi', methods=['POST'])
def trigger_uzi_analysis(code):
    """触发 UZI 深度分析"""
    market = request.args.get('market', 'sh')
    task_id = f"{code}_{int(time.time())}"

    with uzi_tasks_lock:
        uzi_tasks[task_id] = {'status': 'running'}

    t = threading.Thread(target=_run_uzi_analysis, args=(code, market, task_id), daemon=True)
    t.start()

    return jsonify({'task_id': task_id, 'status': 'running'})


@app.route('/api/stock/<code>/uzi/status')
def uzi_analysis_status(code):
    """查询 UZI 分析状态"""
    with uzi_tasks_lock:
        candidates = {k: v for k, v in uzi_tasks.items() if k.startswith(f"{code}_")}
        if not candidates:
            return jsonify({'status': 'no_task'})
        latest_id = sorted(candidates.keys())[-1]
        return jsonify({'task_id': latest_id, **candidates[latest_id]})


@app.route('/uzi/<path:filename>')
def serve_uzi_report(filename):
    """提供 UZI 生成的 HTML 报告"""
    return send_from_directory(UZI_STATIC_DIR, filename)


'''
    insert_pos = content.find("@app.route('/api/scan')")
    content = content[:insert_pos] + uzi_endpoints + content[insert_pos:]

    with open(SERVER_PY, 'w', encoding='utf-8') as f:
        f.write(content)
    print("✓ UZI 代码已插入 server.py")

# 验证无误
import py_compile
py_compile.compile(SERVER_PY, doraise=True)
print("✓ 语法检查通过")
