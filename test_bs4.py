import baostock as bs
import sys
bs.login()
code = "sh.603993"
year = 2025

# Test individually
print("Testing query_profit_data...", flush=True)
try:
    rs = bs.query_profit_data(code, year, 4)
    print(f"  err={rs.error_code} {rs.error_msg}", flush=True)
except Exception as e:
    print(f"  EXCEPTION: {e}", flush=True)

print("Testing query_balance_data...", flush=True)
try:
    rs = bs.query_balance_data(code, year, 4)
    print(f"  err={rs.error_code} {rs.error_msg}", flush=True)
except Exception as e:
    print(f"  EXCEPTION: {e}", flush=True)

bs.logout()
print("DONE", flush=True)
