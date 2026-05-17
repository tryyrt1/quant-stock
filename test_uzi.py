#!/usr/bin/env python3
"""Test UZI run.py directly"""
import subprocess, sys, time

code = sys.argv[1] if len(sys.argv) > 1 else "sh600519"

print(f"[test] Running UZI for {code} with 120s timeout...")
start = time.time()
try:
    proc = subprocess.run(
        ["python3", "run.py", code, "--depth", "lite", "--no-browser"],
        cwd="/home/ubuntu/UZI-Skill",
        capture_output=True, text=True, timeout=120
    )
    elapsed = time.time() - start
    print(f"[test] Completed in {elapsed:.0f}s")
    print(f"[test] stdout ({len(proc.stdout)} bytes):")
    print(proc.stdout[-500:])
    if proc.stderr:
        print(f"[test] stderr ({len(proc.stderr)} bytes):")
        print(proc.stderr[-500:])
except subprocess.TimeoutExpired:
    print(f"[test] TIMEOUT after {time.time()-start:.0f}s")
except Exception as e:
    print(f"[test] ERROR: {e}")

# Check reports
import glob, os
reports = glob.glob(f"/home/ubuntu/UZI-Skill/skills/deep-analysis/scripts/reports/{code}_*/full-report-standalone.html")
print(f"[test] Reports found: {reports}")
