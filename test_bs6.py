import baostock as bs
bs.login()

code = "sh.603993"

rs = bs.query_profit_data(code, 2025, 4)
print("err:", rs.error_code, rs.error_msg)
print("fields:", rs.fields)
print("data:", rs.data)
print()

if rs.error_code == "0":
    count = 0
    while rs.next():
        count += 1
        vals = {f: getattr(rs, f, None) for f in rs.fields}
        print(f"Row {count}: {vals}")
        if count >= 3:
            break
    print(f"Total rows in iteration: {count}")

rs = bs.query_balance_data(code, 2025, 4)
print("\nbalance err:", rs.error_code, rs.error_msg)
print("balance data:", rs.data)

bs.logout()
