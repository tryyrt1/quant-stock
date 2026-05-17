import baostock as bs
import sys
bs.login()
code = "sh.603993"
year = 2025

print("Testing query_profit_data iteration...", flush=True)
rs = bs.query_profit_data(code, year, 4)
print(f"  err={rs.error_code} {rs.error_msg}", flush=True)
if rs.error_code == "0":
    count = 0
    while rs.next():
        count += 1
        if count <= 2:
            print(f"  row {count}: first few fields={rs.fields[:5]} values={[getattr(rs, f, None) for f in rs.fields[:5]]}", flush=True)
        if count > 10:
            print(f"  TOO MANY ROWS (>{count}), breaking", flush=True)
            break
    print(f"  total rows={count}", flush=True)
try:
    rs.free()
except:
    pass

bs.logout()
print("DONE", flush=True)
