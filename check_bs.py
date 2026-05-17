import baostock as bs
bs.login()
for name in ('query_balance_data', 'query_profit_data', 'query_performance_express_report', 'query_debtpaying_data'):
    fn = getattr(bs, name, None)
    print(name, 'EXISTS' if fn else 'MISSING')

rs = bs.query_balance_data("sh.603993", "query", 2025, "4")
print('balance error:', rs.error_code, rs.error_msg)
if rs.error_code == '0':
    while rs.next():
        f = [x for x in dir(rs) if not x.startswith('_')]
        print('balance fields:', f)
        break

rs = bs.query_performance_express_report("sh.603993", "query", 2025, "4")
print('perf error:', rs.error_code, rs.error_msg)
if rs.error_code == '0':
    while rs.next():
        f = [x for x in dir(rs) if not x.startswith('_')]
        print('perf fields:', f)
        break

rs = bs.query_stock_basic("sh.603993")
print('basic error:', rs.error_code, rs.error_msg)
if rs.error_code == '0':
    while rs.next():
        f = [x for x in dir(rs) if not x.startswith('_')]
        print('basic fields:', f)
        break

bs.logout()
