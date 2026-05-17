import baostock as bs
import sys
bs.login()
code = "sh.603993"
year = 2025

for fn_name in ("query_profit_data", "query_balance_data", "query_operation_data",
                 "query_growth_data", "query_cash_flow_data", "query_dupont_data"):
    print(f"Testing {fn_name}...", flush=True)
    fn = getattr(bs, fn_name)
    rs = fn(code, year, "4")
    print(f"  err={rs.error_code}", flush=True)
    if rs.error_code == "0":
        count = 0
        while rs.next():
            count += 1
        print(f"  rows={count}", flush=True)
    try:
        rs.free()
    except:
        pass

bs.logout()
print("DONE")
