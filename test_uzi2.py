#!/usr/bin/env python3
"""Test UZI run.py with partial output"""
import subprocess, sys, time, os, signal

code = sys.argv[1] if len(sys.argv) > 1 else "sh600519"

print(f"[test] Running UZI for {code}...", flush=True)
start = time.time()
proc = subprocess.Popen(
    ["python3", "run.py", code, "--depth", "lite", "--no-browser"],
    cwd="/home/ubuntu/UZI-Skill",
    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    text=True
)

# Wait up to 180s with periodic status
elapsed = 0
while elapsed < 180:
    try:
        proc.wait(timeout=10)
        break
    except subprocess.TimeoutExpired:
        elapsed += 10
        print(f"[test] Still running after {elapsed}s...", flush=True)

if proc.returncode is None:
    os.kill(proc.pid, signal.SIGTERM)
    proc.wait()
    print(f"[test] KILLED after {elapsed}s", flush=True)
else:
    print(f"[test] Completed in {elapsed}s, returncode={proc.returncode}", flush=True)

stdout = proc.stdout.read() if proc.stdout else ""
stderr = proc.stderr.read() if proc.stderr else ""
print(f"[test] stdout ({len(stdout)} bytes):", flush=True)
print(stdout[-1000:] if stdout else "(empty)", flush=True)
if stderr:
    print(f"[test] stderr ({len(stderr)} bytes):", flush=True)
    print(stderr[-1000:], flush=True)

# Check reports
import glob
reports = glob.glob(f"/home/ubuntu/UZI-Skill/skills/deep-analysis/scripts/reports/{code}_*/full-report-standalone.html")
print(f"[test] Reports: {reports}", flush=True)
