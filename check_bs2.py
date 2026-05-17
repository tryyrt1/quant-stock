import baostock as bs
bs.login()

rs = bs.query_balance_data("sh.603993", 2025, 4)
print("balance err:", rs.error_code, rs.error_msg)
if rs.error_code == "0":
    while rs.next():
        f = [x for x in dir(rs) if not x.startswith("_")]
        print("balance fields:", f)
        for field in f:
            print(f"  {field} = {getattr(rs, field)}")
        break

rs = bs.query_cash_flow_data("sh.603993", 2025, 4)
print("cashflow err:", rs.error_code, rs.error_msg)
if rs.error_code == "0":
    while rs.next():
        f = [x for x in dir(rs) if not x.startswith("_")]
        print("cashflow fields:", f)
        for field in f:
            print(f"  {field} = {getattr(rs, field)}")
        break

bs.logout()
