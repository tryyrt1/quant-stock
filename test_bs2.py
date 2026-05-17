import baostock as bs
bs.login()

code = "sh.603993"
for year in (2025, 2024, 2023):
    for fn_name in ("query_balance_data", "query_operation_data", "query_growth_data",
                     "query_cash_flow_data", "query_dupont_data"):
        fn = getattr(bs, fn_name)
        rs = fn(code, year, "4")
        print(f"{fn_name}({year}): err={rs.error_code}")
        if rs.error_code == "0":
            count = 0
            while rs.next():
                count += 1
                row = {}
                for field in rs.fields:
                    val = getattr(rs, field, None)
                    if val == "" or val is None:
                        val = None
                    else:
                        try:
                            val = float(val)
                        except:
                            pass
                    row[field] = val
                if count == 1:
                    print(f"  fields={rs.fields[:6]}... vals={list(row.values())[:6]}...")
            print(f"  rows={count}")
        try:
            rs.free()
        except:
            pass

bs.logout()
print("DONE")
