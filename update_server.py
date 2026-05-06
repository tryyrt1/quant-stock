#!/usr/bin/env python3
import urllib.request, os

base = "https://raw.githubusercontent.com/tryyrt1/quant-stock/main"
files = ["engine/stock_list.py", "server.py"]

for f in files:
    url = f"{base}/{f}"
    print(f"Downloading {f}...", end=" ")
    try:
        data = urllib.request.urlopen(url, timeout=30).read()
        path = os.path.join("/home/ubuntu/quant-stock", f)
        with open(path, "wb") as fh:
            fh.write(data)
        print(f"OK ({len(data)} bytes)")
    except Exception as e:
        print(f"FAIL: {e}")
