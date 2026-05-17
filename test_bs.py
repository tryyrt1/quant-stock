import baostock as bs
bs.login()
rs = bs.query_balance_data("sh.603993", 2025, 4)
print("ERR:", rs.error_code, rs.error_msg)
if rs.error_code == "0":
    while rs.next():
        print("FIELDS:", rs.fields)
        print("DATA:", rs.data)
        break
bs.logout()
print("DONE")
