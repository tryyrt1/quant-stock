#!/usr/bin/env python3
"""Test UZI with long timeout"""
import subprocess, sys, time, os, signal

code = sys.argv[1] if len(sys.argv) > 1 else "sh600519"

print(f"[test] Running UZI for {code} with 500s timeout...", flush=True)
start = time.time()
proc = subprocess.Popen(
    ["python3", "run.py", code, "--depth", "lite", "--no-browser"],
    cwd="/home/ubuntu/UZI-Skill",
    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
)

elapsed = 0
while elapsed < 500:
    try:
        proc.wait(timeout=30)
        break
    except subprocess.TimeoutExpired:
        elapsed += 30
        print(f"[test] Still running after {elapsed}s...", flush=True)

if proc.returncode is None:
    os.kill(proc.pid, signal.SIGTERM)
    proc.wait()
    print(f"[test] KILLED after {elapsed+30}s", flush=True)
else:
    print(f"[test] Completed in {time.time()-start:.0f}s, returncode={proc.returncode}", flush=True)

stdout = proc.stdout.read() if proc.stdout else ""
stderr = proc.stderr.read() if proc.stderr else ""
print(f"[test] stdout last 500 chars:", flush=True)
print(stdout[-500:], flush=True)
if stderr:
    print(f"[test] stderr last 500 chars:", flush=True)
    print(stderr[-500:], flush=True)

import glob
reports = glob.glob(f"/home/ubuntu/UZI-Skill/skills/deep-analysis/scripts/reports/{code}_*/full-report-standalone.html")
print(f"[test] Reports: {reports}", flush=True)
