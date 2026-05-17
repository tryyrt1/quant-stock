import baostock as bs
bs.login()
rs = bs.query_stock_basic("sh.603993")
print("fields:", rs.fields)
print("data:", rs.data)
rs = bs.query_stock_industry("sh.603993")
print("industry fields:", rs.fields)
print("industry data:", rs.data)
bs.logout()
