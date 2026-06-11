"""AI 量化选股系统 - 主服务器 (单文件版)"""
import json, os, socket, sys, re, time, threading, shutil, subprocess
from datetime import datetime
from flask import Flask, jsonify, request, Response, send_from_directory

import hashlib
from flask import session, redirect, url_for
from functools import wraps

APP_PASSWORD = os.environ.get('APP_PASSWORD', 'changeme')

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('auth') or session.get('auth') != hashlib.md5(APP_PASSWORD.encode()).hexdigest():
            if request.path.startswith('/api/') and '/api/system/status' not in request.path:
                return jsonify({'error': '需要密码认证，请在首页输入密码'}), 401
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated

# ─── 数据源配置 ───
DATA_SOURCE = "auto"  # auto | tencent | baostock
BAOSTOCK_INSTALLED = False
try:
    import baostock as bs
    lg = bs.login()
    if lg.error_code == '0': BAOSTOCK_INSTALLED = True
    bs.logout()
except: pass

AKSHARE_AVAILABLE = False
try:
    import akshare as ak
    AKSHARE_AVAILABLE = True
except: pass

def get_active_data_source():
    if DATA_SOURCE == "baostock" and BAOSTOCK_INSTALLED:
        return "baostock"
    return "tencent"

# 静态文件输出目录（排雷/技术评分等写入此目录）
UZI_STATIC_DIR = os.path.join(os.path.dirname(__file__), 'static', 'uzi')

from engine.indicators import *
from engine.factors import analyze_factors
from engine.news import fetch_news, analyze_sentiment
from engine.patterns import scan_patterns
from engine.sectors import search_sectors, get_sector_stocks, scan_sector_stocks, fetch_hot_boards, PREDEFINED
from engine.decision import make_decision
from engine.prediction_tracker import record_prediction, verify_predictions, update_prediction_tracks, is_record_time, is_trading_day, get_stock_stats, get_recent_results, record_nextday_prediction, verify_nextday_predictions, get_nextday_stats

# 活跃股票内置名单 (深市主板+沪市主板, 排除创业板/科创板/ST)
STATIC_STOCKS = [
    ("600519","sh","贵州茅台"),("600036","sh","招商银行"),("600900","sh","长江电力"),
    ("600887","sh","伊利股份"),("600030","sh","中信证券"),("600276","sh","恒瑞医药"),
    ("601318","sh","中国平安"),("600585","sh","海螺水泥"),("601166","sh","兴业银行"),
    ("600000","sh","浦发银行"),("600104","sh","上汽集团"),("600809","sh","山西汾酒"),
    ("600309","sh","万华化学"),("600028","sh","中国石化"),("600941","sh","中国移动"),
    ("601088","sh","中国神华"),("601225","sh","陕西煤业"),("601985","sh","中国核电"),
    ("601668","sh","中国建筑"),("600690","sh","海尔智家"),("601899","sh","紫金矿业"),
    ("600438","sh","通威股份"),("600031","sh","三一重工"),("600150","sh","中国船舶"),
    ("600048","sh","保利发展"),("600383","sh","金地集团"),("601688","sh","华泰证券"),
    ("601398","sh","工商银行"),("601939","sh","建设银行"),("601288","sh","农业银行"),
    ("601328","sh","交通银行"),("600016","sh","民生银行"),
    ("600196","sh","复星医药"),("600085","sh","同仁堂"),("600600","sh","青岛啤酒"),
    ("600660","sh","福耀玻璃"),("600009","sh","上海机场"),("600886","sh","国投电力"),
    ("000001","sz","平安银行"),("000002","sz","万科A"),("000333","sz","美的集团"),
    ("000651","sz","格力电器"),("000858","sz","五粮液"),("000568","sz","泸州老窖"),
    ("000538","sz","云南白药"),("000625","sz","长安汽车"),("000725","sz","京东方A"),
    ("000100","sz","TCL科技"),("000063","sz","中兴通讯"),("000776","sz","广发证券"),
    ("000423","sz","东阿阿胶"),("000895","sz","双汇发展"),("000338","sz","潍柴动力"),
    ("000408","sz","藏格矿业"),("000932","sz","华菱钢铁"),("000157","sz","中联重科"),
    ("000400","sz","许继电气"),("000425","sz","徐工机械"),("000661","sz","长春高新"),
    ("000792","sz","盐湖股份"),("000800","sz","一汽解放"),("000830","sz","鲁西化工"),
    ("000876","sz","新希望"),("000938","sz","紫光股份"),
    ("000963","sz","华东医药"),("000975","sz","银泰黄金"),("000977","sz","浪潮信息"),
    ("000983","sz","山西焦煤"),("000988","sz","华工科技"),("000999","sz","华润三九"),
    ("002001","sz","新和成"),("002007","sz","华兰生物"),("002008","sz","大族激光"),
    ("002024","sz","苏宁易购"),("002027","sz","分众传媒"),("002032","sz","苏泊尔"),
    ("002049","sz","紫光国微"),("002050","sz","三花智控"),("002056","sz","横店东磁"),
    ("002074","sz","国轩高科"),("002080","sz","中材科技"),("002092","sz","中泰化学"),
    ("002129","sz","中环股份"),("002152","sz","广电运通"),("002155","sz","湖南黄金"),
    ("002156","sz","通富微电"),("002179","sz","中航光电"),("002185","sz","华天科技"),
    ("002202","sz","金风科技"),("002230","sz","科大讯飞"),("002236","sz","大华股份"),
    ("002241","sz","歌尔股份"),("002252","sz","上海莱士"),("002271","sz","东方雨虹"),
    ("002304","sz","洋河股份"),("002311","sz","海大集团"),("002352","sz","顺丰控股"),
    ("002371","sz","北方华创"),("002410","sz","广联达"),("002415","sz","海康威视"),
    ("002459","sz","晶澳科技"),("002460","sz","赣锋锂业"),("002466","sz","天齐锂业"),
    ("002475","sz","立讯精密"),("002493","sz","荣盛石化"),("002555","sz","三七互娱"),
    ("002568","sz","百润股份"),("002594","sz","比亚迪"),("002601","sz","龙佰集团"),
    ("002602","sz","世纪华通"),("002603","sz","以岭药业"),("002607","sz","中公教育"),
    ("002624","sz","完美世界"),("002625","sz","光启技术"),("002648","sz","卫星化学"),
    ("002709","sz","天赐材料"),("002714","sz","牧原股份"),("002736","sz","国信证券"),
    ("002739","sz","万达电影"),("002756","sz","永兴材料"),("002791","sz","坚朗五金"),
    ("002812","sz","恩捷股份"),("002821","sz","凯莱英"),("002841","sz","视源股份"),
    ("002850","sz","科达利"),("002867","sz","周大生"),("002916","sz","深南电路"),
    ("002920","sz","德赛西威"),("002938","sz","鹏鼎控股"),("002945","sz","华林证券"),
    ("002959","sz","小熊电器"),("002965","sz","祥鑫科技"),("003816","sz","中国广核"),
    ("601012","sh","隆基绿能"),("601238","sh","广汽集团"),("601633","sh","长城汽车"),
    ("601689","sh","拓普集团"),("601877","sh","正泰电器"),("601888","sh","中国中免"),
    ("601919","sh","中远海控"),("601658","sh","邮储银行"),
    ("601995","sh","中金公司"),("601236","sh","红塔证券"),("601066","sh","中信建投"),
    ("601878","sh","浙商证券"),("601336","sh","新华保险"),
    ("601600","sh","中国铝业"),("601618","sh","中国中冶"),("601669","sh","中国电建"),
    ("601800","sh","中国交建"),("601868","sh","中国能建"),("601390","sh","中国中铁"),
    ("601186","sh","中国铁建"),("601611","sh","中国核建"),("601766","sh","中国中车"),
    ("601615","sh","明阳智能"),("601727","sh","上海电气"),("601898","sh","中煤能源"),
    ("601958","sh","金钼股份"),("603259","sh","药明康德"),("603288","sh","海天味业"),
    ("603160","sh","汇顶科技"),("603993","sh","洛阳钼业"),("603799","sh","华友钴业"),
    ("603986","sh","兆易创新"),("603501","sh","韦尔股份"),("603456","sh","九洲药业"),
    ("603658","sh","安图生物"),("603833","sh","欧派家居"),("603899","sh","晨光股份"),
    ("603185","sh","上机数控"),("603260","sh","合盛硅业"),("603806","sh","福斯特"),
    ("603659","sh","璞泰来"),("603444","sh","吉比特"),("603195","sh","公牛集团"),
    ("603233","sh","大参林"),("603883","sh","老百姓"),("603939","sh","益丰药房"),
    ("605117","sh","德业股份"),("605499","sh","东鹏饮料"),("605090","sh","九丰能源"),
    ("605358","sh","立昂微"),("605111","sh","新洁能"),("605376","sh","博迁新材"),
    ("600004","sh","白云机场"),("600006","sh","东风汽车"),("600010","sh","包钢股份"),
    ("600011","sh","华能国际"),("600018","sh","上港集团"),("600019","sh","宝钢股份"),
    ("600021","sh","上海电力"),("600023","sh","浙能电力"),("600025","sh","华能水电"),
    ("600026","sh","中远海能"),("600029","sh","南方航空"),("600039","sh","四川路桥"),
    ("600050","sh","中国联通"),("600061","sh","国投资本"),("600062","sh","华润双鹤"),
    ("600066","sh","宇通客车"),("600079","sh","人福医药"),("600085","sh","同仁堂"),
    ("600089","sh","特变电工"),("600096","sh","云天化"),("600100","sh","同方股份"),
    ("600109","sh","国金证券"),("600111","sh","北方稀土"),("600115","sh","中国东航"),
    ("600118","sh","中国卫星"),("600132","sh","重庆啤酒"),("600141","sh","兴发集团"),
    ("600143","sh","金发科技"),("600150","sh","中国船舶"),("600153","sh","建发股份"),
    ("600160","sh","巨化股份"),("600161","sh","天坛生物"),("600166","sh","福田汽车"),
    ("600170","sh","上海建工"),("600171","sh","上海贝岭"),("600176","sh","中国巨石"),
    ("600177","sh","雅戈尔"),("600183","sh","生益科技"),("600188","sh","兖矿能源"),
    ("600196","sh","复星医药"),("600199","sh","金种子酒"),("600200","sh","江苏吴中"),
    ("600201","sh","生物股份"),("600206","sh","有研新材"),("600208","sh","新湖中宝"),
    ("600219","sh","南山铝业"),("600221","sh","海南航空"),("600222","sh","太龙药业"),
    ("600223","sh","鲁商发展"),("600226","sh","瀚叶股份"),("600229","sh","城市传媒"),
    ("600230","sh","沧州大化"),("600231","sh","凌钢股份"),("600233","sh","圆通速递"),
    ("600236","sh","桂冠电力"),("600237","sh","铜峰电子"),("600238","sh","海南椰岛"),
    ("600239","sh","云南城投"),("600246","sh","万通发展"),("600252","sh","中恒集团"),
    ("600255","sh","鑫科材料"),("600256","sh","广汇能源"),("600257","sh","大湖股份"),
    ("600258","sh","首旅酒店"),("600259","sh","广晟有色"),("600260","sh","凯乐科技"),
    ("600261","sh","阳光照明"),("600262","sh","北方股份"),("600266","sh","城建发展"),
    ("600267","sh","海正药业"),("600268","sh","国电南自"),("600271","sh","航天信息"),
    ("600272","sh","开开实业"),("600273","sh","嘉化能源"),("600276","sh","恒瑞医药"),
    ("600277","sh","亿利洁能"),("600278","sh","东方创业"),("600280","sh","中央商场"),
    ("600281","sh","华阳新材"),("600282","sh","南钢股份"),("600283","sh","钱江水利"),
    ("600284","sh","浦东建设"),("600285","sh","羚锐制药"),("600287","sh","江苏舜天"),
    ("600288","sh","大恒科技"),("600292","sh","远达环保"),("600293","sh","三峡新材"),
    ("600295","sh","鄂尔多斯"),("600297","sh","广汇汽车"),("600298","sh","安琪酵母"),
    ("600299","sh","安迪苏"),("600300","sh","维维股份"),("600301","sh","华锡有色"),
    ("600302","sh","标准股份"),("600303","sh","ST曙光"),("600305","sh","恒顺醋业"),
    ("600306","sh","*ST商城"),("600307","sh","酒钢宏兴"),("600308","sh","华泰股份"),
    ("600309","sh","万华化学"),("600310","sh","广西能源"),("600311","sh","*ST荣华"),
    ("600312","sh","平高电气"),("600313","sh","农发种业"),("600315","sh","上海家化"),
    ("600316","sh","洪都航空"),("600317","sh","营口港"),("600318","sh","新力金融"),
    ("600319","sh","*ST亚星"),("600320","sh","振华重工"),("600321","sh","正源股份"),
    ("600322","sh","津投城开"),("600323","sh","瀚蓝环境"),("600325","sh","华发股份"),
    ("600326","sh","西藏天路"),("600327","sh","大东方"),("600328","sh","中盐化工"),
    ("600329","sh","达仁堂"),("600330","sh","天通股份"),("600331","sh","宏达股份"),
    ("600332","sh","白云山"),("600333","sh","长春燃气"),("600335","sh","国机汽车"),
    ("600336","sh","澳柯玛"),("600337","sh","美克家居"),("600338","sh","西藏珠峰"),
    ("600339","sh","中油工程"),("600340","sh","华夏幸福"),("600343","sh","航天动力"),
    ("600345","sh","长江通信"),("600346","sh","恒力石化"),("600348","sh","华阳股份"),
    ("600350","sh","山东高速"),("600351","sh","亚宝药业"),("600352","sh","浙江龙盛"),
    ("600353","sh","旭光电子"),("600354","sh","敦煌种业"),("600355","sh","精伦电子"),
    ("600356","sh","恒丰纸业"),("600358","sh","国旅联合"),("600359","sh","新农开发"),
    ("600360","sh","华微电子"),("600361","sh","创新新材"),("600362","sh","江西铜业"),
    ("600363","sh","联创光电"),("600365","sh","ST通葡"),("600366","sh","宁波韵升"),
    ("600367","sh","红星发展"),("600368","sh","五洲交通"),("600369","sh","西南证券"),
    ("600370","sh","*ST交投"),("600371","sh","万向德农"),("600372","sh","中航电子"),
    ("600373","sh","中文传媒"),("600375","sh","汉马科技"),("600376","sh","首开股份"),
    ("600377","sh","宁沪高速"),("600378","sh","昊华科技"),("600379","sh","宝光股份"),
    ("600380","sh","健康元"),("600381","sh","青海春天"),("600382","sh","广东明珠"),
    ("600383","sh","金地集团"),("600386","sh","北巴传媒"),("600387","sh","海越能源"),
    ("600388","sh","龙净环保"),("600389","sh","江山股份"),("600390","sh","五矿资本"),
    ("600391","sh","航发科技"),("600392","sh","盛和资源"),("600393","sh","ST粤泰"),
    ("600395","sh","盘江股份"),("600396","sh","金山股份"),("600397","sh","安源煤业"),
    ("600398","sh","海澜之家"),("600399","sh","抚顺特钢"),("600400","sh","红豆股份"),
    ("600403","sh","大有能源"),("600405","sh","动力源"),("600406","sh","国电南瑞"),
    ("600408","sh","安泰集团"),("600409","sh","三友化工"),("600410","sh","华胜天成"),
    ("600415","sh","小商品城"),("600416","sh","湘电股份"),("600418","sh","江淮汽车"),
    ("600419","sh","天润乳业"),("600420","sh","国药现代"),("600422","sh","昆药集团"),
    ("600423","sh","柳化股份"),("600425","sh","青松建化"),("600426","sh","华鲁恒升"),
    ("600428","sh","中远海特"),("600429","sh","三元股份"),("600433","sh","冠豪高新"),
    ("600435","sh","北方导航"),("600436","sh","片仔癀"),("600438","sh","通威股份"),
    ("600439","sh","瑞贝卡"),("600444","sh","国机通用"),("600446","sh","金证股份"),
    ("600448","sh","华纺股份"),("600449","sh","宁夏建材"),("600452","sh","涪陵电力"),
    ("600455","sh","博通股份"),("600456","sh","宝钛股份"),("600458","sh","时代新材"),
    ("600459","sh","贵研铂业"),("600460","sh","士兰微"),("600461","sh","洪城环境"),
    ("600462","sh","ST九有"),("600463","sh","空港股份"),("600466","sh","蓝光发展"),
    ("600467","sh","好当家"),("600468","sh","百利电气"),("600469","sh","风神股份"),
    ("600470","sh","六国化工"),("600475","sh","华光环能"),("600476","sh","湘邮科技"),
    ("600477","sh","杭萧钢构"),("600478","sh","科力远"),("600479","sh","千金药业"),
    ("600480","sh","凌云股份"),("600481","sh","双良节能"),("600482","sh","中国动力"),
    ("600483","sh","福能股份"),("600486","sh","扬农化工"),("600487","sh","亨通光电"),
    ("600488","sh","津药药业"),("600489","sh","中金黄金"),("600490","sh","鹏欣资源"),
    ("600491","sh","龙元建设"),("600493","sh","凤竹纺织"),("600495","sh","晋西车轴"),
    ("600496","sh","精工钢构"),("600497","sh","驰宏锌锗"),("600498","sh","烽火通信"),
    ("600499","sh","科达制造"),("600500","sh","中化国际"),("600501","sh","航天晨光"),
    ("600502","sh","安徽建工"),("600503","sh","华丽家族"),("600505","sh","西昌电力"),
    ("600506","sh","统一股份"),("600507","sh","方大特钢"),("600508","sh","上海能源"),
    ("600509","sh","天富能源"),("600510","sh","黑牡丹"),("600511","sh","国药股份"),
    ("600512","sh","腾达建设"),("600513","sh","联环药业"),("600515","sh","海南机场"),
    ("600516","sh","方大炭素"),("600517","sh","国网英大"),("600518","sh","ST康美"),
    ("600519","sh","贵州茅台"),("600520","sh","文一科技"),("600521","sh","华海药业"),
    ("600522","sh","中天科技"),("600523","sh","贵航股份"),("600525","sh","长园集团"),
    ("600526","sh","菲达环保"),("600527","sh","江南高纤"),("600528","sh","中铁工业"),
    ("600529","sh","山东药玻"),("600530","sh","交大昂立"),("600531","sh","豫光金铅"),
    ("600532","sh","*ST未来"),("600533","sh","栖霞建设"),("600535","sh","天士力"),
    ("600536","sh","中国软件"),("600537","sh","亿晶光电"),("600538","sh","国发股份"),
    ("600539","sh","狮头股份"),("600540","sh","新赛股份"),("600543","sh","莫高股份"),
    ("600545","sh","卓郎智能"),("600546","sh","山煤国际"),("600547","sh","山东黄金"),
    ("600548","sh","深高速"),("600549","sh","厦门钨业"),("600550","sh","保变电气"),
    ("600551","sh","时代出版"),("600552","sh","凯盛科技"),("600556","sh","天下秀"),
    ("600557","sh","康缘药业"),("600558","sh","大西洋"),("600559","sh","老白干酒"),
    ("600560","sh","金自天正"),("600561","sh","江西长运"),("600562","sh","国睿科技"),
    ("600563","sh","法拉电子"),("600565","sh","迪马股份"),("600566","sh","济川药业"),
    ("600567","sh","山鹰国际"),("600568","sh","ST中珠"),("600569","sh","安阳钢铁"),
    ("600570","sh","恒生电子"),("600571","sh","信雅达"),("600572","sh","康恩贝"),
    ("600573","sh","惠泉啤酒"),("600575","sh","淮河能源"),("600576","sh","祥源文化"),
    ("600577","sh","精达股份"),("600578","sh","京能电力"),("600579","sh","克劳斯"),
    ("600580","sh","卧龙电驱"),("600581","sh","八一钢铁"),("600582","sh","天地科技"),
    ("600583","sh","海油工程"),("600584","sh","长电科技"),("600585","sh","海螺水泥"),
    ("600586","sh","金晶科技"),("600587","sh","新华医疗"),("600588","sh","用友网络"),
    ("600589","sh","广东榕泰"),("600590","sh","泰豪科技"),("600592","sh","龙溪股份"),
    ("600593","sh","大连圣亚"),("600594","sh","益佰制药"),("600595","sh","中孚实业"),
    ("600596","sh","新安股份"),("600597","sh","光明乳业"),("600598","sh","北大荒"),
    ("600599","sh","ST熊猫"),("600600","sh","青岛啤酒"),("600601","sh","方正科技"),
    ("600602","sh","云赛智联"),("600603","sh","广汇物流"),("600604","sh","市北高新"),
    ("600605","sh","汇通能源"),("600606","sh","绿地控股"),("600607","sh","上实医药"),
    ("600609","sh","金杯汽车"),("600610","sh","中毅达"),("600611","sh","大众交通"),
    ("600612","sh","老凤祥"),("600613","sh","神奇制药"),("600614","sh","退市鹏起"),
    ("600615","sh","*ST丰华"),("600616","sh","金枫酒业"),("600617","sh","国新能源"),
    ("600618","sh","氯碱化工"),("600619","sh","海立股份"),("600620","sh","天宸股份"),
    ("600621","sh","华鑫股份"),("600622","sh","光大嘉宝"),("600623","sh","华谊集团"),
    ("600624","sh","复旦复华"),("600626","sh","申达股份"),("600628","sh","新世界"),
    ("600629","sh","华建集团"),("600630","sh","龙头股份"),("600633","sh","浙数文化"),
    ("600635","sh","大众公用"),("600636","sh","国新文化"),("600637","sh","东方明珠"),
    ("600638","sh","新黄浦"),("600639","sh","浦东金桥"),("600640","sh","国脉文化"),
    ("600641","sh","万业企业"),("600642","sh","申能股份"),("600643","sh","爱建集团"),
    ("600644","sh","乐山电力"),("600645","sh","中源协和"),("600648","sh","外高桥"),
    ("600649","sh","城投控股"),("600650","sh","锦江在线"),("600651","sh","飞乐音响"),
    ("600652","sh","*ST游久"),("600653","sh","申华控股"),("600655","sh","豫园股份"),
    ("600657","sh","信达地产"),("600658","sh","电子城"),("600660","sh","福耀玻璃"),
    ("600661","sh","昂立教育"),("600662","sh","外服控股"),("600663","sh","陆家嘴"),
    ("600664","sh","哈药股份"),("600665","sh","天地源"),("600666","sh","ST瑞德"),
    ("600667","sh","太极实业"),("600668","sh","尖峰集团"),("600671","sh","ST目药"),
    ("600673","sh","东阳光"),("600674","sh","川投能源"),("600675","sh","中华企业"),
    ("600676","sh","交运股份"),("600677","sh","*ST航通"),("600678","sh","四川金顶"),
    ("600679","sh","上海凤凰"),("600681","sh","百川能源"),("600682","sh","南京新百"),
    ("600683","sh","京投发展"),("600684","sh","珠江股份"),("600685","sh","中船防务"),
    ("600686","sh","金龙汽车"),("600687","sh","*ST刚泰"),("600688","sh","上海石化"),
    ("600689","sh","上海三毛"),("600690","sh","海尔智家"),("600691","sh","阳煤化工"),
    ("600692","sh","亚通股份"),("600693","sh","东百集团"),("600694","sh","大商股份"),
    ("600695","sh","退市绿庭"),("600696","sh","岩石股份"),("600697","sh","欧亚集团"),
    ("600698","sh","湖南天雁"),("600699","sh","均胜电子"),("600702","sh","舍得酒业"),
    ("600703","sh","三安光电"),("600704","sh","物产中大"),("600705","sh","中航产融"),
    ("600706","sh","曲江文旅"),("600707","sh","彩虹股份"),("600708","sh","光明地产"),
    ("600710","sh","苏美达"),("600711","sh","盛屯矿业"),("600712","sh","南宁百货"),
    ("600713","sh","南京医药"),("600714","sh","金瑞矿业"),("600715","sh","文投控股"),
    ("600716","sh","凤凰股份"),("600717","sh","天津港"),("600718","sh","东软集团"),
    ("600719","sh","大连热电"),("600720","sh","中交设计"),("600721","sh","百花医药"),
    ("600722","sh","金牛化工"),("600723","sh","首商股份"),("600724","sh","宁波富达"),
    ("600725","sh","云维股份"),("600726","sh","华电能源"),("600727","sh","鲁北化工"),
    ("600728","sh","佳都科技"),("600729","sh","重庆百货"),("600730","sh","中国高科"),
    ("600731","sh","湖南海利"),("600732","sh","爱旭股份"),("600733","sh","北汽蓝谷"),
    ("600734","sh","ST实达"),("600735","sh","新华锦"),("600736","sh","苏州高新"),
    ("600737","sh","中粮糖业"),("600738","sh","丽尚国潮"),("600739","sh","辽宁成大"),
    ("600740","sh","山西焦化"),("600741","sh","华域汽车"),("600742","sh","一汽富维"),
    ("600743","sh","华远地产"),("600744","sh","华银电力"),("600745","sh","闻泰科技"),
    ("600746","sh","江苏索普"),("600748","sh","上实发展"),("600749","sh","西藏旅游"),
    ("600750","sh","江中药业"),("600751","sh","海航科技"),("600753","sh","东方银星"),
    ("600754","sh","锦江酒店"),("600755","sh","厦门国贸"),("600756","sh","浪潮软件"),
    ("600757","sh","长江传媒"),("600758","sh","辽宁能源"),("600759","sh","洲际油气"),
    ("600760","sh","中航沈飞"),("600761","sh","安徽合力"),("600763","sh","通策医疗"),
    ("600764","sh","中国海防"),("600765","sh","中航重机"),("600766","sh","*ST园城"),
    ("600767","sh","*ST运盛"),("600768","sh","宁波富邦"),("600769","sh","祥龙电业"),
    ("600770","sh","综艺股份"),("600771","sh","广誉远"),("600773","sh","西藏城投"),
    ("600774","sh","汉商集团"),("600775","sh","南京熊猫"),("600776","sh","东方通信"),
    ("600777","sh","新潮能源"),("600778","sh","友好集团"),("600779","sh","水井坊"),
    ("600780","sh","通宝能源"),("600781","sh","*ST辅仁"),("600782","sh","新钢股份"),
    ("600783","sh","鲁信创投"),("600784","sh","鲁银投资"),("600785","sh","新华百货"),
    ("600787","sh","中储股份"),("600789","sh","鲁抗医药"),("600790","sh","轻纺城"),
    ("600791","sh","京能置业"),("600792","sh","云煤能源"),("600793","sh","宜宾纸业"),
    ("600794","sh","保税科技"),("600795","sh","国电电力"),("600796","sh","钱江生化"),
    ("600797","sh","浙大网新"),("600798","sh","宁波海运"),("600800","sh","渤海化学"),
    ("600801","sh","华新水泥"),("600802","sh","福建水泥"),("600803","sh","新奥股份"),
    ("600804","sh","鹏博士"),("600805","sh","悦达投资"),("600807","sh","济南高新"),
    ("600808","sh","马钢股份"),("600809","sh","山西汾酒"),("600810","sh","神马股份"),
    ("600811","sh","东方集团"),("600812","sh","华北制药"),("600814","sh","杭州解百"),
    ("600815","sh","厦工股份"),("600816","sh","建元信托"),("600817","sh","宇通重工"),
    ("600818","sh","中路股份"),("600819","sh","耀皮玻璃"),("600820","sh","隧道股份"),
    ("600821","sh","金开新能"),("600822","sh","上海物贸"),("600823","sh","世茂股份"),
    ("600824","sh","益民集团"),("600825","sh","新华传媒"),("600826","sh","兰生股份"),
    ("600827","sh","百联股份"),("600828","sh","茂业商业"),("600829","sh","人民同泰"),
    ("600830","sh","香溢融通"),("600831","sh","广电网络"),("600833","sh","第一医药"),
    ("600834","sh","申通地铁"),("600835","sh","上海机电"),("600836","sh","上海易连"),
    ("600837","sh","海通证券"),("600838","sh","上海九百"),("600839","sh","四川长虹"),
    ("600841","sh","动力新科"),("600843","sh","上工申贝"),("600844","sh","丹化科技"),
    ("600845","sh","宝信软件"),("600846","sh","同济科技"),("600847","sh","万里股份"),
    ("600848","sh","上海临港"),("600850","sh","电科数字"),("600851","sh","海欣股份"),
    ("600853","sh","龙建股份"),("600854","sh","春兰股份"),("600855","sh","航天长峰"),
    ("600856","sh","*ST中天"),("600857","sh","宁波中百"),("600858","sh","银座股份"),
    ("600859","sh","王府井"),("600860","sh","京城股份"),("600861","sh","北京城乡"),
    ("600862","sh","中航高科"),("600863","sh","内蒙华电"),("600864","sh","哈投股份"),
    ("600865","sh","百大集团"),("600866","sh","星湖科技"),("600867","sh","通化东宝"),
    ("600868","sh","梅雁吉祥"),("600869","sh","远东股份"),("600871","sh","石化油服"),
    ("600872","sh","中炬高新"),("600873","sh","梅花生物"),("600874","sh","创业环保"),
    ("600875","sh","东方电气"),("600876","sh","凯盛新能"),("600877","sh","电能股份"),
    ("600879","sh","航天电子"),("600880","sh","博瑞传播"),("600881","sh","亚泰集团"),
    ("600882","sh","妙可蓝多"),("600883","sh","博闻科技"),("600884","sh","杉杉股份"),
    ("600885","sh","宏发股份"),("600886","sh","国投电力"),("600887","sh","伊利股份"),
    ("600888","sh","新疆众和"),("600889","sh","南京化纤"),("600890","sh","中房股份"),
    ("600892","sh","大晟文化"),("600893","sh","航发动力"),("600894","sh","广日股份"),
    ("600895","sh","张江高科"),("600896","sh","*ST海医"),("600897","sh","厦门空港"),
    ("600898","sh","ST美讯"),("600900","sh","长江电力"),("600901","sh","江苏金租"),
    ("600903","sh","贵州燃气"),("600905","sh","三峡能源"),("600906","sh","财达证券"),
    ("600908","sh","无锡银行"),("600909","sh","华安证券"),("600916","sh","中国黄金"),
    ("600917","sh","重庆燃气"),("600918","sh","中泰证券"),("600919","sh","江苏银行"),
    ("600926","sh","杭州银行"),("600928","sh","西安银行"),("600929","sh","雪天盐业"),
    ("600933","sh","爱柯迪"),("600936","sh","广西广电"),("600939","sh","重庆建工"),
    ("600941","sh","中国移动"),("600956","sh","新天绿能"),("600958","sh","东方证券"),
    ("600959","sh","江苏有线"),("600960","sh","渤海汽车"),("600961","sh","株冶集团"),
    ("600962","sh","国投中鲁"),("600963","sh","岳阳林纸"),("600965","sh","福成股份"),
    ("600966","sh","博汇纸业"),("600967","sh","内蒙一机"),("600968","sh","海油发展"),
    ("600969","sh","郴电国际"),("600970","sh","中材国际"),("600971","sh","恒源煤电"),
    ("600973","sh","宝胜股份"),("600975","sh","新五丰"),("600976","sh","健民集团"),
    ("600977","sh","中国电影"),("600979","sh","广安爱众"),("600980","sh","北矿科技"),
    ("600981","sh","汇鸿集团"),("600982","sh","宁波能源"),("600983","sh","惠而浦"),
    ("600984","sh","建设机械"),("600985","sh","淮北矿业"),("600986","sh","浙文互联"),
    ("600987","sh","航民股份"),("600988","sh","赤峰黄金"),("600989","sh","宝丰能源"),
    ("600990","sh","四创电子"),("600992","sh","贵绳股份"),("600993","sh","马应龙"),
    ("600995","sh","南网储能"),("600996","sh","贵广网络"),("600997","sh","开滦股份"),
    ("600998","sh","九州通"),("600999","sh","招商证券"),
]

app = Flask(__name__, static_folder='static')
app.secret_key = os.urandom(24).hex()
DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
WATCHLIST_FILE = os.path.join(DATA_DIR, 'watchlist.json')
REALTIME_CACHE = {}  # {code: {data, time}}

# 确保数据目录和自选股文件存在 (gunicorn 下也会执行)
os.makedirs(DATA_DIR, exist_ok=True)
if not os.path.exists(WATCHLIST_FILE):
    with open(WATCHLIST_FILE, 'w', encoding='utf-8') as f:
        json.dump([], f)

# =================== 工具函数 ===================

def load_watchlist():
    try:
        with open(WATCHLIST_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return []

def save_watchlist(wl):
    with open(WATCHLIST_FILE, 'w', encoding='utf-8') as f:
        json.dump(wl, f, ensure_ascii=False, indent=2)

def fetch_tencent_quote(codes_str):
    """获取腾讯实时行情"""
    url = f'https://qt.gtimg.cn/q={codes_str}'
    import requests
    r = requests.get(url, timeout=8, headers={'User-Agent': 'Mozilla/5.0'})
    r.encoding = 'gbk'
    results = []
    for line in r.text.split('\n'):
        m = re.search(r'v_[a-z]+\d+="(.+)"', line)
        if not m: continue
        f = m.group(1).split('~')
        if len(f) < 40: continue
        results.append({
            'code': f[2], 'name': f[1],
            'price': _f(f[3]), 'yesterdayClose': _f(f[4]),
            'open': _f(f[5]), 'volume': _int(f[6]),
            'high': _f(f[33]), 'low': _f(f[34]),
            'change': _f(f[31]), 'changePercent': _f(f[32]),
            'turnover': _f(f[38]), 'pe': _f(f[39]),
            'pb': _f(f[46]),
        })
    return {r['code']: r for r in results}

def fetch_kline(code_str, days=120, period='day'):
    """获取K线数据, period: 'day' 或 'week'"""
    url = f'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={code_str},{period},,,{days},qfq'
    import requests
    r = requests.get(url, timeout=8, headers={'User-Agent': 'Mozilla/5.0'})
    raw = r.json()
    data = raw.get('data', {})
    wk_key = f'qfq{period}'
    klines = data.get(code_str, {}).get(wk_key) or data.get(code_str, {}).get(period) or []
    return [{'date': k[0], 'open': _f(k[1]), 'close': _f(k[2]),
             'high': _f(k[3]), 'low': _f(k[4]), 'volume': _int(k[5])} for k in klines]

def _f(v):
    try: return float(v)
    except: return 0.0
def _int(v):
    try: return int(float(v))
    except: return 0

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        return s.getsockname()[0]
    except:
        return '127.0.0.1'
    finally:
        s.close()

# =================== API 路由 ===================

@app.route('/login', methods=['GET', 'POST'])
def login_page():
    if request.method == 'POST':
        pwd = request.form.get('password', '')
        if pwd == APP_PASSWORD:
            session['auth'] = hashlib.md5(APP_PASSWORD.encode()).hexdigest()
            return redirect('/')
        return '<html><body style="background:#1a1a3e;color:#fff;font-family:sans-serif;display:flex;justify-content:center;align-items:center;height:100vh"><div style="text-align:center"><h2>密码错误</h2><a href="/login" style="color:#00d2ff">重新输入</a></div></body></html>'
    return '''<html><body style="background:#1a1a3e;color:#fff;font-family:sans-serif;display:flex;justify-content:center;align-items:center;height:100vh">
<form method="post" style="text-align:center;padding:40px;background:rgba(255,255,255,.05);border-radius:12px">
<h2 style="margin-bottom:20px">AI 量化选股系统</h2>
<input type="password" name="password" placeholder="请输入密码" style="padding:10px 20px;font-size:16px;border:1px solid #333;border-radius:6px;background:#222;color:#fff;width:200px">
<br><br>
<button type="submit" style="padding:10px 40px;font-size:16px;background:#00d2ff;color:#000;border:none;border-radius:6px;cursor:pointer">进入</button>
</form></body></html>'''

@app.route('/')
@require_auth
def index():
    resp = send_from_directory('static', 'index.html')
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    # 服务端直渲染系统状态
    try:
        status_html = _get_system_status_html()
        resp.set_data(resp.get_data().decode('utf-8').replace(
            '<span id="statusText">加载中...</span>',
            '<span id="statusText" style="color:#888">' + status_html + '</span>'
        ).encode('utf-8'))
    except:
        pass
    return resp

def _get_system_status_html():
    from engine.weight_optimizer import get_weight_summary
    from engine.ml_scorer import is_ready, FEATURE_FILE
    import os, json
    parts = []
    if is_ready():
        t = ''
        if os.path.exists(FEATURE_FILE):
            try: t = ' (' + json.load(open(FEATURE_FILE)).get('trained_at','')[:10] + ')'
            except: pass
        parts.append(f'ML评分{t}')
    ws = get_weight_summary()
    if '动态' in ws: parts.append('动态权重')
    parts.append('周线分析')
    parts.append('量价四形态')
    parts.append('主力控盘度')
    parts.append('尾盘监控')
    parts.append('下跌原因分析')
    return ' | '.join(parts)

    return '', 204
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp

@app.route('/favicon.ico')
def favicon():
    return '', 204

@app.route('/api/watchlist', methods=['GET', 'POST', 'DELETE'])
def watchlist_api():
    wl = load_watchlist()

    if request.method == 'GET':
        return jsonify(wl)

    if request.method == 'POST':
        item = request.json
        # 格式: {code, market, name} 或 {code: '600519', market: 'sh'}
        code = item.get('code', '')
        market = item.get('market', 'sh')
        name = item.get('name', code)

        if not code:
            return jsonify({'error': '缺少股票代码'}), 400

        exists = any(s['code'] == code and s['market'] == market for s in wl)
        if not exists:
            wl.insert(0, {'code': code, 'market': market, 'name': name, 'added': time.strftime('%Y-%m-%d')})
            save_watchlist(wl)

        return jsonify(wl)

    if request.method == 'DELETE':
        code = request.args.get('code', '')
        market = request.args.get('market', 'sh')
        wl = [s for s in wl if not (s['code'] == code and s['market'] == market)]
        save_watchlist(wl)
        return jsonify(wl)


@app.route('/api/quote')
def quote_api():
    codes_str = request.args.get('codes', '')
    if not codes_str:
        return jsonify({'error': 'missing codes'}), 400
    data = fetch_tencent_quote(codes_str)
    return jsonify(data)


@app.route('/api/kline')
def kline_api():
    code = request.args.get('code', '')
    days = int(request.args.get('days', 120))
    if not code:
        return jsonify({'error': 'missing code'}), 400
    data = fetch_kline(code, days)
    return jsonify(data)


@app.route('/api/stock/<code>')
def stock_detail(code):
    """股票综合分析"""
    market = request.args.get('market', 'sh')
    full_code = market + code

    # 并行获取数据
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as exe:
        f_quote = exe.submit(fetch_tencent_quote, full_code)
        f_kline = exe.submit(fetch_kline, full_code, 120)
        f_news = exe.submit(fetch_news, code, market)

    try:
        quotes = f_quote.result()
    except Exception as e:
        print(f'[stock_detail] {code} 获取行情失败: {e}')
        quotes = {}
    try:
        kline = f_kline.result()
    except Exception as e:
        print(f'[stock_detail] {code} 获取K线失败: {e}')
        kline = []
    try:
        news_raw = f_news.result()
    except Exception as e:
        print(f'[stock_detail] {code} 获取新闻失败: {e}')
        news_raw = []

    quote = quotes.get(code, {}) if quotes else {}

    # 情感分析
    sentiment_score, news_analyzed = analyze_sentiment(news_raw)

    # 压力位/支撑位 (先算，因子分析要用)
    from engine.indicators import calc_support_resistance
    sr = calc_support_resistance(kline) if len(kline) >= 20 else {}

    # 因子分析
    factors = analyze_factors(kline, quote, sentiment_score, sr) if len(kline) >= 60 else {'score': 50, 'advice': '数据不足'}

    # 技术指标概要
    closes = [k['close'] for k in kline]
    indicators = {}
    if len(closes) >= 60:
        rsi = calc_rsi(closes, 14)
        macd = calc_macd(closes)
        indicators = {
            'rsi': round(rsi[-1], 2) if rsi[-1] else None,
            'macd_dif': round(macd['dif'][-1], 3) if macd['dif'] else None,
            'macd_dea': round(macd['dea'][-1], 3) if macd['dea'] else None,
            'macd': round(macd['macd'][-1], 3) if macd['macd'] else None,
            'ma5': round(calc_ma(closes, 5)[-1], 2) if calc_ma(closes, 5)[-1] else None,
            'ma20': round(calc_ma(closes, 20)[-1], 2) if calc_ma(closes, 20)[-1] else None,
            'ma60': round(calc_ma(closes, 60)[-1], 2) if calc_ma(closes, 60)[-1] else None,
        }

    # 主力控盘度
    mfc_result = {}
    try:
        idx_k = fetch_kline('sh000001', 30)
        from engine.indicators import calc_main_force_control
        turnover = quote.get('turnover', 0) if quote else 0
        sentiment_score_local = sentiment_score if 'sentiment_score' in dir() else 0
        mfc_result = calc_main_force_control(kline, turnover_rate=turnover, news_sentiment=sentiment_score, index_klines=idx_k)
    except Exception as e:
        print(f'[stock_detail] {code} 主力控盘度失败: {e}')

    # 量价关系（双版本）
    vp_result = {}
    if len(kline) >= 60:
        try:
            from engine.indicators import classify_vp_relationship, classify_vp_weekly
            vp_result = {
                'daily': classify_vp_relationship(kline),
                'weekly': classify_vp_weekly(kline) if len(kline) >= 10 else {'type':'正常','label':'数据不足','color':'gray'},
            }
        except Exception as e:
            print(f'[stock_detail] {code} 量价关系失败: {e}')

    return jsonify({
        'code': code,
        'market': market,
        'quote': quote,
        'kline': kline[-60:],
        'indicators': indicators,
        'factors': factors,
        'sr': sr,
        'news': news_analyzed[:10],
        'sentiment': round(sentiment_score, 2),
        'data_source': get_active_data_source(),
        'vp': vp_result,
        'mfc': mfc_result,
    })


# ─── 综合决策 API ───

@app.route('/api/stock/<code>/decision')
def stock_decision_api(code):
    """综合买卖决策: 整合技术/形态/量价/板块, 输出明确信号"""
    market = request.args.get('market', 'sh')
    full_code = market + code

    # 获取 K 线
    kline = fetch_kline(full_code, 120)
    if not kline or len(kline) < 20:
        return jsonify({"error": "K线数据不足", "signal": "数据不足", "score": 0})

    closes = [k['close'] for k in kline]

    # 获取行情
    quotes = fetch_tencent_quote(full_code)
    quote = quotes.get(code, {}) if quotes else {}

    # 支撑/压力位
    from engine.indicators import calc_support_resistance
    sr = calc_support_resistance(kline) if len(kline) >= 20 else {}

    # 形态识别
    pat_results = scan_patterns({full_code: kline}) if len(kline) >= 20 else {}
    patterns = pat_results.get(full_code, [])

    # 板块上下文 (从最新板块快照获取)
    sector_ctx = _find_sector_context(code)

    decision = make_decision(closes, kline, patterns, sr, sector_ctx, quote=quote, code=code, market=market)

    # 附带当前价格和涨跌幅
    decision["price"] = quote.get("price", 0)
    decision["change_pct"] = quote.get("changePercent", 0)
    decision["name"] = quote.get("name", "")
    decision["code"] = code

    return jsonify(decision)


# ─── 预测回测 API ───

@app.route('/api/predictions/stats')
def predictions_stats_api():
    """次日预测统计（自选股）"""
    return jsonify(get_nextday_stats())


@app.route('/api/predictions/verify', methods=['POST'])
def predictions_verify_api():
    """手动触发验证"""
    count = verify_predictions(fetch_kline)
    stats = get_signal_stats()
    stats["verified_count"] = count
    return jsonify(stats)


@app.route('/api/predictions/recent')
def predictions_recent_api():
    """近N天验证结果"""
    days = request.args.get('days', 7, type=int)
    return jsonify(get_recent_results(days))


@app.route('/api/predictions/performance')
def predictions_performance_api():
    """信号历史表现：各信号类型在不同持有期的平均收益率和胜率"""
    return jsonify(get_signal_performance())


@app.route('/api/predictions/diagnose')
def predictions_diagnose_api():
    """自动诊断: 分析各信号准确率，找出最准的方法并给出建议"""
    return jsonify(auto_diagnose())


@app.route('/api/predictions/methods/stats')
def predictions_methods_stats_api():
    """各方法多时间维度准确率统计"""
    return jsonify(get_method_multi_offset_stats())


@app.route('/api/predictions/methods/<code>')
def predictions_method_snapshot_api(code):
    """个股方法快照"""
    return jsonify(get_stock_method_snapshot(code))


# ─── 主力成本分析 ───

def estimate_capital_cost(code, market, klines=None):
    """估算主力资金成本价
    方法1: 成交量分布 (Volume Profile) — 将每根K线量分配到日内高低区间，找量能最密集的价格带
    方法2: 主力建仓痕迹 — 放量上涨日的加权均价
    返回: {method1: {}, method2: {}, composite: {}}
    """
    if klines is None:
        klines = fetch_kline(market + code, 120)

    result = {"method1": {}, "method2": {}, "composite": {}}
    if not klines or len(klines) < 20:
        return result

    closes = [k["close"] for k in klines]
    current_price = closes[-1]
    avg_vol = sum(k["volume"] for k in klines) / len(klines)

    # ── 方法1: 成交量分布 (Volume Profile) ──
    # 将价格区间分成25个桶，每根K线的量按比例分配到当日高低价覆盖的桶
    all_highs = [k["high"] for k in klines]
    all_lows = [k["low"] for k in klines]
    max_price = max(all_highs)
    min_price = min(all_lows)
    price_range = max_price - min_price

    if price_range < 0.01:
        return result

    num_buckets = 25
    bucket_size = price_range / num_buckets

    buckets = [min_price + (i + 0.5) * bucket_size for i in range(num_buckets)]
    vol_profile = [0.0] * num_buckets

    for k in klines:
        vol = k["volume"]
        low = k["low"]
        high = k["high"]
        day_range = high - low
        if day_range <= 0:
            continue
        start_idx = max(0, int((low - min_price) / bucket_size))
        end_idx = min(num_buckets - 1, int((high - min_price) / bucket_size))
        bins = end_idx - start_idx + 1
        vol_per_bin = vol / bins
        for i in range(start_idx, end_idx + 1):
            vol_profile[i] += vol_per_bin

    # POC — 量最大的价格
    poc_idx = vol_profile.index(max(vol_profile))
    poc_price = buckets[poc_idx]

    # 价值区间 (VA) — 从POC向两边扩展，直到包含70%总成交量
    total_vol_all = sum(vol_profile)
    va_vol_target = total_vol_all * 0.7
    va_vol = vol_profile[poc_idx]
    va_low_idx = va_high_idx = poc_idx
    while va_vol < va_vol_target:
        left_vol = vol_profile[va_low_idx - 1] if va_low_idx > 0 else 0
        right_vol = vol_profile[va_high_idx + 1] if va_high_idx < num_buckets - 1 else 0
        if left_vol >= right_vol and va_low_idx > 0:
            va_low_idx -= 1
            va_vol += left_vol
        elif va_high_idx < num_buckets - 1:
            va_high_idx += 1
            va_vol += right_vol
        else:
            break

    va_high = buckets[va_high_idx]
    va_low = buckets[va_low_idx]

    # VA内VWAP
    va_vwap_total_vol = sum(vol_profile[va_low_idx:va_high_idx + 1])
    va_vwap_total_val = sum(buckets[i] * vol_profile[i] for i in range(va_low_idx, va_high_idx + 1))
    va_vwap = va_vwap_total_val / va_vwap_total_vol if va_vwap_total_vol > 0 else current_price

    # 成本区间显示: 取VA内的最低最高价(不是全量范围)
    pct_above_vp = (current_price - va_vwap) / va_vwap * 100 if va_vwap else 0
    signal = "主力成本区下方" if pct_above_vp < -3 else "主力成本区附近" if abs(pct_above_vp) < 3 else "主力成本区上方"

    result["method1"] = {
        "vp_cost": round(va_vwap, 2),
        "poc": round(poc_price, 2),
        "va_low": round(va_low, 2),
        "va_high": round(va_high, 2),
        "current_price": round(current_price, 2),
        "pct_above_cost": round(pct_above_vp, 2),
        "signal": signal,
    }

    # ── 方法2: 主力建仓痕迹 — 放量上涨日 ──
    accumulation_days = []
    for i in range(1, len(klines)):
        k = klines[i]
        pk = klines[i - 1]
        # 放量上涨: volume > 1.5x 均量, 收阳, 收盘高于昨收
        if (k["volume"] > avg_vol * 1.5
                and k["close"] > k["open"]
                and k["close"] > pk["close"]):
            accumulation_days.append(k)

    if accumulation_days:
        acc_vol = sum(k["volume"] for k in accumulation_days)
        acc_vwap = sum(k["close"] * k["volume"] for k in accumulation_days) / acc_vol
        acc_min = min(k["close"] for k in accumulation_days)
        acc_max = max(k["close"] for k in accumulation_days)
        pct_above_acc = (current_price - acc_vwap) / acc_vwap * 100 if acc_vwap else 0
        result["method2"] = {
            "acc_cost": round(acc_vwap, 2),
            "acc_low": round(acc_min, 2),
            "acc_high": round(acc_max, 2),
            "acc_days": len(accumulation_days),
            "pct_above_cost": round(pct_above_acc, 2),
            "signal": "建仓区下方" if pct_above_acc < -3 else "建仓区附近" if abs(pct_above_acc) < 3 else "建仓区上方",
        }

    # ── 综合判断 ──
    prices_info = []
    if result["method1"].get("vp_cost"):
        prices_info.append(("量分布成本", result["method1"]["vp_cost"]))
    if result["method2"].get("acc_cost"):
        prices_info.append(("建仓成本", result["method2"]["acc_cost"]))

    if prices_info:
        avg_cost = sum(p[1] for p in prices_info) / len(prices_info)
        composite_pct = (current_price - avg_cost) / avg_cost * 100 if avg_cost else 0
        result["composite"] = {
            "avg_cost": round(avg_cost, 2),
            "current_price": round(current_price, 2),
            "pct_above_cost": round(composite_pct, 2),
            "judgment": "主力大概率盈利" if composite_pct > 5 else "主力成本附近" if abs(composite_pct) < 5 else "主力可能被套",
            "sources": [p[0] for p in prices_info],
        }

    return result


@app.route('/api/stock/<code>/capital')
def stock_capital_api(code):
    """主力资金成本分析：量价分布 + 大宗交易 + 多周期均线参考"""
    market = request.args.get('market', 'sh')
    full_code = market + code
    kline = fetch_kline(full_code, 250)  # 一年约250个交易日
    if kline is None:
        kline = []
    result = estimate_capital_cost(code, market, kline)
    result["code"] = code
    result["name"] = ""

    # ── 多周期均线参考成本 ──
    closes = [k["close"] for k in kline]
    ma_periods = [60, 120, 250]
    ma_refs = {}
    for p in ma_periods:
        if len(closes) >= p:
            val = sum(closes[-p:]) / p
            pct = (closes[-1] - val) / val * 100 if val else 0
            ma_refs[f"MA{p}"] = {
                "cost": round(val, 2),
                "pct_above": round(pct, 2),
            }
    if ma_refs:
        result["ma_references"] = ma_refs

    # ── 全周期 VWAP 参考成本 ──
    if len(closes) >= 20:
        try:
            total_vol = sum(k["volume"] for k in kline)
            total_val = sum(k["close"] * k["volume"] for k in kline)
            if total_vol > 0:
                vwap = total_val / total_vol
                vwap_pct = (closes[-1] - vwap) / vwap * 100
                result["vwap_ref"] = {
                    "cost": round(vwap, 2),
                    "pct_above": round(vwap_pct, 2),
                }
        except Exception:
            pass

    # 取最新行情获取名称
    quotes = fetch_tencent_quote(full_code)
    q = quotes.get(code, {})
    if q:
        result["name"] = q.get("name", "")
    return jsonify(result)


@app.route('/api/dailypick/refresh')
def dailypick_refresh_api():
    if os.path.exists(DAILYPICK_FILE):
        try: os.remove(DAILYPICK_FILE)
        except: pass
    period, _, _ = get_dailypick_period()
    try:
        compute_daily_pick(period)
        return jsonify({'status': 'ready', 'message': 'ok'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})


@app.route('/api/weekly/<code>')
def weekly_analysis_api(code):
    """周线分析"""
    market = request.args.get('market', 'sh')
    full_code = market + code
    wk = fetch_kline(full_code, 60, period='week')
    if not wk or len(wk) < 4:
        return jsonify({'error': '周线数据不足', 'code': code})
    from engine.weekly import assess_weekly
    result = assess_weekly(wk)
    result["code"] = code
    result["market"] = market
    result["kline_count"] = len(wk)
    try:
        q = fetch_tencent_quote(full_code)
        if q and q.get(code):
            result["name"] = q[code].get("name", "")
            result["price"] = q[code].get("price", 0)
            result["change_pct"] = q[code].get("changePercent", 0)
    except:
        pass
    return jsonify(result)


# ─── 后台任务存储（排雷/技术评分等） ───
uzi_tasks = {}
uzi_tasks_lock = threading.Lock()


@app.route('/api/datasource', methods=['GET', 'POST'])
def datasource_switch():
    global DATA_SOURCE
    if request.method == 'POST':
        ds = request.json.get('source', 'auto')
        if ds in ('auto', 'tencent', 'baostock'):
            DATA_SOURCE = ds
    return jsonify({
        'source': DATA_SOURCE,
        'active': get_active_data_source(),
        'baostock_installed': BAOSTOCK_INSTALLED
    })


@app.route('/uzi/<path:filename>')
def serve_uzi_output(filename):
    """提供后台任务生成的静态文件（排雷报告等）"""
    return send_from_directory(UZI_STATIC_DIR, filename)


# ─── 财报排雷 (Minesweeper) ───
MINESWEEPER_DIR = os.path.join(os.path.dirname(__file__), '..', 'github-skills', 'financial-report-minesweeper')

def _run_minesweeper(code, task_id):
    try:
        os.makedirs(UZI_STATIC_DIR, exist_ok=True)
        script_file = os.path.join(MINESWEEPER_DIR, 'scripts', 'minesweeper_baostock.py')
        if not os.path.exists(script_file):
            script_file = os.path.join(MINESWEEPER_DIR, 'scripts', 'minesweeper_data.py')
        log_file = os.path.join(UZI_STATIC_DIR, f"{code}_ms.log")
        python_cmd = "python3" if os.path.exists("/usr/bin/python3") else "python"
        cmd = [python_cmd, script_file, "--stock-code", code, "--years", "3"]
        with open(log_file, "w", encoding="utf-8") as log:
            subprocess.run(cmd, cwd=MINESWEEPER_DIR, stdout=log, stderr=log, timeout=120)
        # 从日志文件中提取 JSON 输出 (minesweeper_baostock 打印 JSON 到 stdout)
        import re as _re
        with open(log_file, "r", encoding="utf-8") as log:
            content = log.read()
        json_match = _re.search(r'\{.*', content, _re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
            dest = os.path.join(UZI_STATIC_DIR, f"{code}_minesweeper.json")
            with open(dest, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            with uzi_tasks_lock:
                uzi_tasks[task_id] = {"status": "done", "url": f"/uzi/{code}_minesweeper.json"}
        else:
            # 尝试读取旧格式输出文件
            out_file = os.path.join(MINESWEEPER_DIR, "output", code, "financial_data.json")
            if os.path.exists(out_file):
                with open(out_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                dest = os.path.join(UZI_STATIC_DIR, f"{code}_minesweeper.json")
                with open(dest, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                with uzi_tasks_lock:
                    uzi_tasks[task_id] = {"status": "done", "url": f"/uzi/{code}_minesweeper.json"}
            else:
                with uzi_tasks_lock:
                    uzi_tasks[task_id] = {"status": "error", "msg": "排雷数据未生成"}
    except Exception as e:
        with uzi_tasks_lock:
            uzi_tasks[task_id] = {"status": "error", "msg": str(e)}

@app.route('/api/stock/<code>/minesweeper', methods=['POST'])
def trigger_minesweeper(code):
    task_id = f"ms_{code}_{int(time.time())}"
    with uzi_tasks_lock:
        uzi_tasks[task_id] = {"status": "running"}
    t = threading.Thread(target=_run_minesweeper, args=(code, task_id), daemon=True)
    t.start()
    return jsonify({'task_id': task_id, 'status': 'running'})

@app.route('/api/stock/<code>/minesweeper/status')
def minesweeper_status(code):
    with uzi_tasks_lock:
        candidates = {k: v for k, v in uzi_tasks.items() if k.startswith(f"ms_{code}_")}
        if not candidates:
            return jsonify({'status': 'no_task'})
        latest_id = sorted(candidates.keys())[-1]
        return jsonify({'task_id': latest_id, **candidates[latest_id]})


# ─── Openclaw 技术深度评分 ───
OPENCLAW_DIR = os.path.join(os.path.dirname(__file__), '..', 'github-skills', 'openclaw-stock-analyzer')

def _run_openclaw(code, task_id):
    try:
        os.makedirs(UZI_STATIC_DIR, exist_ok=True)
        log_file = os.path.join(UZI_STATIC_DIR, f"{code}_oc.log")
        cmd = ["python", "stock_data_fetcher.py", "--stocks", code, "--days", "120"]
        with open(log_file, "w", encoding="utf-8") as log:
            subprocess.run(cmd, cwd=MINESWEEPER_DIR, stdout=log, stderr=log, timeout=120)
        # 读取 output
    # 简化版：直接用现有指标做评分（不需要依赖 openclaw）
    except Exception as e:
        with uzi_tasks_lock:
            uzi_tasks[task_id] = {"status": "error", "msg": str(e)}

@app.route('/api/stock/<code>/opencore', methods=['POST'])
def trigger_opencore(code):
    task_id = f"oc_{code}_{int(time.time())}"
    with uzi_tasks_lock:
        uzi_tasks[task_id] = {"status": "running"}
    # 直接用现有数据计算评分，不需要子进程
    with uzi_tasks_lock:
        uzi_tasks[task_id] = {"status": "done", "url": "/api/stock/" + code + "?nocache=1"}
    return jsonify({'task_id': task_id, 'status': 'done'})


# ─── 估值分析 ───
@app.route('/api/stock/<code>/valuation')
def valuation_api(code):
    """个股估值分析：自算 PE/PB vs 市场报价"""
    market = request.args.get('market', 'sz')
    price = request.args.get('price', type=float, default=0)
    if not price:
        code_str = f"{market}{code}"
        q = fetch_tencent_quote(code_str)
        if q and q.get(code):
            price = q[code].get('price', 0)
    if not price:
        return jsonify({'error': '无法获取价格'})
    from engine.valuation import get_valuation
    # 取腾讯行情的 PE/PB 作为对比
    code_str = f"{market}{code}"
    q = fetch_tencent_quote(code_str)
    market_pe = q.get(code, {}).get('pe', 0) if q else 0
    market_pb = q.get(code, {}).get('pb', 0) if q else 0
    result = get_valuation(code, price, market_pe=market_pe or None, market_pb=market_pb or None)
    return jsonify(result)


# ─── 宏观/商品分析 ───
COMMODITIES = [
    # Domestic futures (via futures_zh_daily_sina)
    {"id": "AU0", "name": "沪金", "short": "Gold", "exchange": "SHFE", "type": "domestic"},
    {"id": "AG0", "name": "沪银", "short": "Silver", "exchange": "SHFE", "type": "domestic"},
    {"id": "CU0", "name": "沪铜", "short": "Copper", "exchange": "SHFE", "type": "domestic"},
    {"id": "SC0", "name": "原油", "short": "Crude Oil", "exchange": "INE", "type": "domestic"},
    {"id": "RB0", "name": "螺纹钢", "short": "Rebar", "exchange": "SHFE", "type": "domestic"},
    {"id": "I0",  "name": "铁矿石", "short": "Iron Ore", "exchange": "DCE", "type": "domestic"},
    {"id": "ZN0", "name": "沪锌", "short": "Zinc", "exchange": "SHFE", "type": "domestic"},
    {"id": "AL0", "name": "沪铝", "short": "Aluminum", "exchange": "SHFE", "type": "domestic"},
    # International futures (via futures_foreign_hist)
    {"id": "CL",  "name": "WTI原油", "short": "WTI Crude", "exchange": "NYMEX", "type": "foreign"},
    {"id": "GC",  "name": "COMEX黄金", "short": "Gold", "exchange": "COMEX", "type": "foreign"},
    {"id": "SI",  "name": "COMEX白银", "short": "Silver", "exchange": "COMEX", "type": "foreign"},
    {"id": "HG",  "name": "COMEX铜", "short": "Copper", "exchange": "COMEX", "type": "foreign"},
    {"id": "NG",  "name": "天然气", "short": "Natural Gas", "exchange": "NYMEX", "type": "foreign"},
    {"id": "W",   "name": "美小麦", "short": "Wheat", "exchange": "CBOT", "type": "foreign"},
    {"id": "C",   "name": "美玉米", "short": "Corn", "exchange": "CBOT", "type": "foreign"},
    {"id": "S",   "name": "美大豆", "short": "Soybeans", "exchange": "CBOT", "type": "foreign"},
    # LME real-time (via futures_global_spot_em)
    {"id": "LME_CU", "name": "伦铜", "short": "LME Copper", "exchange": "LME", "type": "lme"},
    {"id": "LME_AL", "name": "伦铝", "short": "LME Aluminum", "exchange": "LME", "type": "lme"},
    {"id": "LME_ZN", "name": "伦锌", "short": "LME Zinc", "exchange": "LME", "type": "lme"},
    {"id": "LME_NI", "name": "伦镍", "short": "LME Nickel", "exchange": "LME", "type": "lme"},
    {"id": "LME_PB", "name": "伦铅", "short": "LME Lead", "exchange": "LME", "type": "lme"},
    {"id": "LME_SN", "name": "伦锡", "short": "LME Tin", "exchange": "LME", "type": "lme"},
]

_LME_SPOT_MAP = {
    'LME_CU': 'LCPT',
    'LME_AL': 'LALT',
    'LME_ZN': 'LZNT',
    'LME_NI': 'LNKT',
    'LME_PB': 'LLDT',
    'LME_SN': 'LTNT',
}

_LME_STOCK_NAMES = {  # column names in macro_euro_lme_stock
    '铜': 'LME_CU', '铝': 'LME_AL', '铅': 'LME_PB',
    '锌': 'LME_ZN', '镍': 'LME_NI', '锡': 'LME_SN',
}

_COMMODITY_CACHE = {}  # {cid: {data, time}}

def fetch_commodity_kline(cid, days=365):
    """获取商品期货主力连续K线 (akshare)"""
    if not AKSHARE_AVAILABLE:
        return None, "akshare 未安装"
    now = time.time()
    cached = _COMMODITY_CACHE.get(cid)
    if cached and now - cached['time'] < 3600:  # 1小时缓存
        return cached['data'], None
    try:
        import akshare as ak
        info = next((c for c in COMMODITIES if c['id'] == cid), None)
        if not info:
            return None, f"未知商品: {cid}"
        ctype = info.get('type')

        # --- LME real-time (no k-line history available) ---
        if ctype == 'lme':
            spot_code = _LME_SPOT_MAP.get(cid)
            if not spot_code:
                return None, f"无 LME 代码映射: {cid}"
            spot_df = ak.futures_global_spot_em()
            if spot_df is None or spot_df.empty:
                return None, "获取 LME 行情失败"
            row = spot_df[spot_df.iloc[:, 1] == spot_code]
            if row.empty:
                return None, f"未找到 {info['name']} 行情"
            r = row.iloc[0]
            price = float(r.iloc[3]) if r.iloc[3] != 'nan' else 0
            open_p = float(r.iloc[6]) if r.iloc[6] != 'nan' else 0
            high = float(r.iloc[7]) if r.iloc[7] != 'nan' else 0
            low = float(r.iloc[8]) if r.iloc[8] != 'nan' else 0
            change = float(r.iloc[4]) if r.iloc[4] != 'nan' else 0
            # 用当前 spot 数据构造 2 根 k 线让涨跌幅计算可用
            today_str = datetime.now().strftime('%Y-%m-%d')
            prev_close = price - change
            kline = [
                {'date': '--', 'open': prev_close, 'high': prev_close, 'low': prev_close, 'close': prev_close, 'volume': 0},
                {'date': today_str, 'open': open_p, 'high': high, 'low': low, 'close': price, 'volume': 0,
                 'change': round(change, 2), 'change_pct': round(change / prev_close * 100, 2) if prev_close else 0},
            ]
            _COMMODITY_CACHE[cid] = {'data': kline, 'time': now}
            return kline, None

        # --- Domestic & foreign ---
        is_foreign = ctype == 'foreign'
        if is_foreign:
            df = ak.futures_foreign_hist(symbol=cid)
        else:
            df = ak.futures_zh_daily_sina(symbol=cid)

        if df is None or df.empty:
            return None, f"未获取到 {cid} 数据"
        df = df.sort_values('date').tail(days)
        kline = []
        for _, row in df.iterrows():
            kline.append({
                'date': str(row['date']),
                'open': float(row['open']),
                'high': float(row['high']),
                'low': float(row['low']),
                'close': float(row['close']),
                'volume': int(row.get('volume', 0) or 0),
            })
        _COMMODITY_CACHE[cid] = {'data': kline, 'time': now}
        return kline, None
    except Exception as e:
        return None, str(e)

def analyze_commodity_trend(kline):
    """分析商品期货趋势，复用 indicators 已有函数"""
    from engine.indicators import calc_ma, calc_rsi, calc_macd, calc_support_resistance
    if not kline or len(kline) < 20:
        return {'short_term': {'direction': '数据不足', 'signal': '', 'strength': ''},
                'long_term': {'direction': '数据不足', 'signal': '', 'strength': ''},
                'composite': '数据不足以分析', 'risk': ''}

    closes = [k['close'] for k in kline]
    cur_price = closes[-1]

    # --- 计算指标 ---
    ma5_arr = calc_ma(closes, 5)
    ma20_arr = calc_ma(closes, 20)
    ma60_arr = calc_ma(closes, 60) if len(closes) >= 60 else [None]*len(closes)
    ma5 = ma5_arr[-1] if ma5_arr[-1] is not None else 0
    ma20 = ma20_arr[-1] if ma20_arr[-1] is not None else 0
    ma60 = ma60_arr[-1] if ma60_arr[-1] is not None else 0

    rsi_arr = calc_rsi(closes, 14)
    rsi = rsi_arr[-1] if rsi_arr[-1] is not None else 50

    macd = calc_macd(closes)
    macd_dif = macd['dif'][-1] if macd['dif'] else 0
    macd_dea = macd['dea'][-1] if macd['dea'] else 0
    macd_val = macd['macd'][-1] if macd['macd'] else 0

    # --- 短期趋势 (MA5 vs MA20) ---
    short_dir = '上涨' if ma5 > ma20 else '下跌' if ma5 < ma20 else '震荡'
    if short_dir == '上涨':
        if ma5 > ma20 and ma20 > ma60:
            short_signal = '多头排列'
        else:
            short_signal = 'MA5>MA20'
    elif short_dir == '下跌':
        if ma5 < ma20 and ma20 < ma60:
            short_signal = '空头排列'
        else:
            short_signal = 'MA5<MA20'
    else:
        short_signal = '均线粘合'

    # 短期强度
    if short_dir == '上涨':
        spread = (ma5 / ma20 - 1) * 100
        short_strength = '强势' if spread > 2 else '较强' if spread > 1 else '温和'
    elif short_dir == '下跌':
        spread = (ma20 / ma5 - 1) * 100
        short_strength = '弱势' if spread > 2 else '较弱' if spread > 1 else '温和'
    else:
        short_strength = '中性'

    # --- 长期趋势 (MA20 vs MA60) ---
    if ma60 > 0:
        long_dir = '上涨' if ma20 > ma60 else '下跌' if ma20 < ma60 else '震荡'
        if long_dir == '上涨':
            spread_l = (ma20 / ma60 - 1) * 100
            long_strength = '强势' if spread_l > 5 else '较强' if spread_l > 2 else '温和'
            long_signal = 'MA20>MA60 多头'
        elif long_dir == '下跌':
            spread_l = (ma60 / ma20 - 1) * 100
            long_strength = '弱势' if spread_l > 5 else '较弱' if spread_l > 2 else '温和'
            long_signal = 'MA20<MA60 空头'
        else:
            long_strength = '中性'
            long_signal = '均线胶着'
    else:
        long_dir = long_signal = long_strength = '数据不足'

    # --- RSI 判断 ---
    rsi_signal = ''
    if rsi > 80: rsi_signal = '严重超买'
    elif rsi > 70: rsi_signal = '超买区间'
    elif rsi < 30: rsi_signal = '超卖区间'
    elif rsi < 20: rsi_signal = '严重超卖'

    # --- MACD 信号 ---
    macd_signal = ''
    if macd_dif > macd_dea and macd_val > 0: macd_signal = 'MACD金叉 多头'
    elif macd_dif < macd_dea and macd_val < 0: macd_signal = 'MACD死叉 空头'
    elif macd_dif > macd_dea: macd_signal = 'DIF上穿DEA'
    elif macd_dif < macd_dea: macd_signal = 'DIF下穿DEA'

    # --- 综合判断 ---
    composite_parts = []
    risk_parts = []

    if short_dir == '上涨' and long_dir == '上涨':
        composite_parts.append('短期和长期均呈上涨趋势')
        composite_parts.append('建议顺势做多')
    elif short_dir == '上涨' and long_dir == '下跌':
        composite_parts.append('短期反弹，长期仍偏空')
        composite_parts.append('建议观望或短线操作')
    elif short_dir == '下跌' and long_dir == '下跌':
        composite_parts.append('短期和长期均呈下跌趋势')
        composite_parts.append('建议回避或做空')
    elif short_dir == '下跌' and long_dir == '上涨':
        composite_parts.append('短期回调，长期趋势未破')
        composite_parts.append('关注支撑位企稳后可做多')
    else:
        composite_parts.append('趋势不明确')
        composite_parts.append('建议观望')

    if rsi_signal:
        risk_parts.append(f'RSI {rsi:.1f} {rsi_signal}')
    if macd_signal:
        risk_parts.append(macd_signal)

    # --- 压力/支撑 ---
    sr = calc_support_resistance(kline)

    return {
        'short_term': {
            'direction': short_dir,
            'signal': short_signal,
            'strength': short_strength,
            'ma5': round(ma5, 2) if ma5 else None,
            'ma20': round(ma20, 2) if ma20 else None,
        },
        'long_term': {
            'direction': long_dir,
            'signal': long_signal,
            'strength': long_strength,
            'ma20': round(ma20, 2) if ma20 else None,
            'ma60': round(ma60, 2) if ma60 else None,
        },
        'rsi': round(rsi, 1) if rsi else None,
        'rsi_signal': rsi_signal,
        'macd': {
            'dif': round(macd_dif, 3) if macd_dif else 0,
            'dea': round(macd_dea, 3) if macd_dea else 0,
            'macd': round(macd_val, 3) if macd_val else 0,
            'signal': macd_signal,
        },
        'composite': '，'.join(composite_parts) if composite_parts else '趋势不明确',
        'risk': '；'.join(risk_parts) if risk_parts else '无明确风险信号',
        'sr': sr,
    }


@app.route('/api/commodity/list')
def commodity_list():
    return jsonify({'commodities': COMMODITIES, 'akshare_available': AKSHARE_AVAILABLE})


@app.route('/api/commodity')
def commodity_detail():
    code = request.args.get('code', 'AU0')
    days = int(request.args.get('days', 365))
    # 查找商品信息
    info = next((c for c in COMMODITIES if c['id'] == code), None)
    if not info:
        return jsonify({'error': f'未知商品: {code}'}), 400

    kline, err = fetch_commodity_kline(code, days)
    if err:
        return jsonify({'error': err}), 500

    # 分析趋势
    trend = analyze_commodity_trend(kline)
    indicators = trend  # trend 已经包含所有技术指标

    # 最近一根K线的涨跌幅
    last = kline[-1] if kline else {}
    prev = kline[-2] if len(kline) >= 2 else {}
    change = round(last.get('close', 0) - prev.get('close', 0), 2) if prev else 0
    change_pct = round(change / prev.get('close', 1) * 100, 2) if prev.get('close', 0) > 0 else 0

    # LME 库存数据
    lme_stock = None
    if info.get('type') == 'lme' and AKSHARE_AVAILABLE:
        try:
            import akshare as ak
            stock_df = ak.macro_euro_lme_stock()
            if stock_df is not None and not stock_df.empty:
                latest = stock_df.iloc[-1]
                date_str = str(latest.iloc[0])
                lme_stock = {'date': date_str, 'items': []}
                for cn_name, cid_inner in _LME_STOCK_NAMES.items():
                    if cid_inner != code:
                        continue
                    # column order: name, Cu-总库存, Cu-注册仓单, Cu-注销仓单
                    for col_idx in range(1, len(latest), 4):
                        metal_name = stock_df.columns[col_idx].split('-')[0]
                        if metal_name == cn_name:
                            lme_stock['items'].append({
                                'total': float(latest.iloc[col_idx]) if latest.iloc[col_idx] else 0,
                                'registered': float(latest.iloc[col_idx + 1]) if latest.iloc[col_idx + 1] else 0,
                                'cancelled': float(latest.iloc[col_idx + 2]) if latest.iloc[col_idx + 2] else 0,
                            })
                            break
        except Exception:
            pass

    resp = {
        'code': code,
        'name': info['name'],
        'short': info['short'],
        'exchange': info['exchange'],
        'type': info.get('type', 'domestic'),
        'kline': kline[-120:],
        'price': round(last.get('close', 0), 2) if last else 0,
        'change': round(last.get('change', change), 2) if last else 0,
        'change_pct': round(last.get('change_pct', change_pct), 2) if last else 0,
        'high': round(last.get('high', 0), 2) if last else 0,
        'low': round(last.get('low', 0), 2) if last else 0,
        'open': round(last.get('open', 0), 2) if last else 0,
        'volume': last.get('volume', 0) if last else 0,
        'trend': trend,
        'data_source': 'akshare',
    }
    if lme_stock:
        resp['lme_stock'] = lme_stock
    return jsonify(resp)


# ─── 板块追踪 API ───

@app.route('/api/sectors/list', methods=['POST'])
def sectors_list_api():
    """解析预设/自定义板块名称 → 板块代码"""
    data = request.json or {}
    names = data.get("names", PREDEFINED)
    board_type = data.get("type", "both")
    result = search_sectors(names, board_type)
    return jsonify({"sectors": result})


@app.route('/api/sectors/scan', methods=['POST'])
def sectors_scan_api():
    """扫描选定板块成分股的技术形态"""
    data = request.json or {}
    sector_codes = data.get("sector_codes", [])
    max_stocks = data.get("max_stocks", 30)
    if not sector_codes:
        return jsonify({"error": "未提供板块代码"}), 400
    result = scan_sector_stocks(sector_codes, fetch_kline, max_stocks=max_stocks)
    return jsonify(result)


@app.route('/api/sectors/heat-history')
def sector_heat_history_api():
    """返回近5日热度前15的板块及进入前10次数"""
    heat_file = os.path.join(DATA_DIR, 'snapshots', 'sector_heat.json')
    if not os.path.exists(heat_file):
        return jsonify([])
    try:
        history = json.load(open(heat_file))
        recent = history[-5:]
        counts = {}
        for day in recent:
            for name in day.get("top10", []):
                counts[name] = counts.get(name, 0) + 1
        ranked = sorted(counts.items(), key=lambda x: -x[1])[:15]
        return jsonify([{"name": n, "count": c} for n, c in ranked])
    except:
        return jsonify([])


@app.route('/api/sectors/hot', methods=['POST'])
def sectors_hot_api():
    """全市场异动板块 Top N（优先从缓存快速读取）"""
    data = request.json or {}
    top_n = data.get("top_n", 30)
    snap_path = os.path.join(DATA_DIR, 'snapshots', 'sectors.json')
    if os.path.exists(snap_path):
        try:
            result = json.load(open(snap_path, encoding='utf-8'))
            sectors = result.get("sectors", [])
            sectors.sort(key=lambda x: -x.get("heat", 0))
            # 缓存不够时实时补扫
            if len(sectors) >= top_n:
                result["sectors"] = sectors[:top_n]
                for i, s in enumerate(result["sectors"]):
                    s["heat_rank"] = i + 1
                return jsonify(result)
        except Exception as e:
            print(f'[sectors_hot] 缓存读取失败: {e}')
    # 缓存不足或不可用时实时扫描
    result = fetch_hot_boards(fetch_kline, top_n=top_n)
    return jsonify(result)


@app.route('/api/sectors/<code>/stocks')
def sector_stocks_api(code):
    """快速获取板块成分股"""
    max_s = request.args.get("max", 50, type=int)
    stocks = get_sector_stocks(code, max_s)
    return jsonify({"sector_code": code, "stocks": stocks, "count": len(stocks)})


@app.route('/api/scan')
def scan_watchlist():
    """扫描自选股，批量分析"""
    wl = load_watchlist()
    if not wl:
        return jsonify({'results': [], 'message': '自选股列表为空'})

    codes_str = ','.join([s['market'] + s['code'] for s in wl])
    quotes = fetch_tencent_quote(codes_str)

    results = []
    for s in wl:
        q = quotes.get(s['code'], {})
        # 简略分析 (详细分析点进去看)
        score = 50
        advice = '持有'
        pe = abs(q.get('pe', 0) or 0)
        if 0 < pe < 20: score += 10
        elif pe > 50: score -= 10
        if q.get('changePercent', 0) > 0: score += 5
        else: score -= 5
        score = max(0, min(100, score))
        if score >= 65: advice = '买入'
        elif score <= 35: advice = '卖出'
        else: advice = '持有'

        results.append({
            'code': s['code'],
            'market': s['market'],
            'name': q.get('name', s.get('name', s['code'])),
            'price': q.get('price', 0),
            'changePercent': q.get('changePercent', 0),
            'change': q.get('change', 0),
            'pe': q.get('pe', 0),
            'score': score,
            'advice': advice,
        })

    results.sort(key=lambda x: x['score'], reverse=True)
    return jsonify({'results': results, 'count': len(results)})


def _find_sector_context(code):
    """从最新板块快照中查找股票所属板块上下文"""
    try:
        snap_path = os.path.join(DATA_DIR, 'snapshots', 'sectors.json')
        if os.path.exists(snap_path):
            with open(snap_path, encoding='utf-8') as f:
                snap = json.load(f)
            for sec in snap.get("sectors", []):
                for stk in sec.get("stocks", []):
                    if stk.get("code") == code:
                        return {
                            "up_count": sec.get("up_count", 0),
                            "down_count": sec.get("down_count", 0),
                            "pattern_count": sec.get("pattern_count", 0),
                            "sector_name": sec.get("name", ""),
                        }
    except Exception:
        pass
    return None


@app.route('/api/scan/deep')
def scan_watchlist_deep():
    """深度分析自选股 — 对每只股票运行完整决策引擎"""
    wl = load_watchlist()
    if not wl:
        return jsonify({'results': [], 'count': 0, 'message': '自选股列表为空'})

    import concurrent.futures

    def analyze_one(s):
        code, market = s['code'], s['market']
        full_code = market + code
        try:
            kline = fetch_kline(full_code, 120)
            if len(kline) < 20:
                return None
            quotes = fetch_tencent_quote(full_code)
            quote = quotes.get(code, {})
            price = quote.get('price', kline[-1]['close'])
            if price <= 0:
                return None

            closes = [k['close'] for k in kline]
            sr = calc_support_resistance(kline)
            pats = scan_patterns({full_code: kline}) if len(kline) >= 20 else {}
            patterns = pats.get(full_code, [])
            sector_ctx = _find_sector_context(code)
            decision = make_decision(closes, kline, patterns, sr, sector_ctx,
                                     quote=quote, code=code, market=market)

            # 风险指标（7方法体系下，5+方法分歧才算严重）
            methods = decision.get('method_signals', {})
            main_signal = decision['signal']
            disagreement = sum(1 for m in methods.values()
                               if m.get('signal') != main_signal)
            near_resistance = sr.get('dist_to_resistance', 999) < 2.0 if sr else False
            capital_outflow = (decision.get('details', {})
                               .get('capital', {}).get('score', 50) < 30)
            high_risk = (disagreement >= 5) + bool(near_resistance) + bool(capital_outflow) >= 2

            return {
                'code': code, 'market': market,
                'name': quote.get('name', s.get('name', code)),
                'price': price,
                'changePercent': quote.get('changePercent', 0),
                'change': quote.get('change', 0),
                'volume': quote.get('volume', 0),
                'pe': quote.get('pe', 0),
                'signal': decision['signal'],
                'sub': decision['sub'],
                'score': decision['score'],
                'color': decision['color'],
                'details': decision['details'],
                'method_signals': methods,
                'reasons': decision.get('reasons', []),
                'sr': {
                    'nearest_resistance': sr.get('nearest_resistance'),
                    'nearest_support': sr.get('nearest_support'),
                    'dist_to_resistance': sr.get('dist_to_resistance'),
                    'dist_to_support': sr.get('dist_to_support'),
                    'resistance_strength': sr.get('resistance_strength'),
                    'support_strength': sr.get('support_strength'),
                } if sr else None,
                'risk_indicators': {
                    'method_disagreement': disagreement,
                    'near_resistance': near_resistance,
                    'capital_outflow': capital_outflow,
                    'high_risk': high_risk,
                },
            }
        except Exception:
            return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as exe:
        results = list(exe.map(analyze_one, wl))

    results = [r for r in results if r is not None]

    # 排序：买入 > 增持 > 持有 > 减仓 > 卖出，同信号按得分降序
    sig_rank = {'买入': 0, '增持': 1, '持有': 2, '减仓': 3, '卖出': 4}
    results.sort(key=lambda r: (sig_rank.get(r['signal'], 9), -r['score']))

    return jsonify({'results': results, 'count': len(results)})


@app.route('/api/watchlist/news')
def watchlist_news():
    """获取所有自选股最新新闻"""
    wl = load_watchlist()
    if not wl:
        return jsonify({'results': [], 'summary': {}, 'updated': ''})

    import concurrent.futures
    from datetime import datetime

    def fetch_one(s):
        code, market = s['code'], s['market']
        try:
            news = fetch_news(code, market)
            sent_score, analyzed = analyze_sentiment(news)
            pos = sum(1 for n in analyzed if n['sentiment'] == 'positive')
            neg = sum(1 for n in analyzed if n['sentiment'] == 'negative')
            neu = sum(1 for n in analyzed if n['sentiment'] == 'neutral')
            return {
                'code': code,
                'market': market,
                'name': s.get('name', code),
                'news': analyzed[:5],
                'sentiment_score': round(sent_score, 2),
                'total_positive': pos,
                'total_negative': neg,
                'total_neutral': neu,
            }
        except Exception:
            return None

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as exe:
        futures = {exe.submit(fetch_one, s): s for s in wl}
        for f in concurrent.futures.as_completed(futures, timeout=20):
            r = f.result()
            if r:
                results.append(r)

    summary = {'positive': 0, 'negative': 0, 'neutral': 0}
    for r in results:
        summary['positive'] += r['total_positive']
        summary['negative'] += r['total_negative']
        summary['neutral'] += r['total_neutral']

    return jsonify({
        'results': results,
        'summary': summary,
        'updated': datetime.now().strftime('%H:%M:%S'),
    })


@app.route('/api/watchlist/predict')
def watchlist_predict():
    """读取今日开盘预测 + 收盘验证 + 次日方向"""
    today = time.strftime('%Y-%m-%d')
    intraday_file = os.path.join(DATA_DIR, 'predictions', 'intraday.json')
    intraday = None
    if os.path.exists(intraday_file):
        try:
            with open(intraday_file, 'r', encoding='utf-8') as f:
                cached = json.load(f)
            if cached.get('date') == today:
                intraday = cached
        except:
            pass

    nd_map = {}
    try:
        nd_file = os.path.join(DATA_DIR, 'predictions', 'nextday.json')
        if os.path.exists(nd_file):
            with open(nd_file, 'r', encoding='utf-8') as f:
                for rec in json.load(f):
                    if rec.get('date') == today:
                        nd_map[rec['code']] = rec
    except:
        pass

    if not intraday:
        return jsonify({'results': [], 'updated': today, 'status': 'waiting', 'message': '等待09:25开盘预测...'})

    results = []
    for r in intraday.get('results', []):
        nd = nd_map.get(r['code'], {})
        results.append({
            'code': r['code'], 'market': r.get('market', 'sh'),
            'name': r.get('name', r['code']),
            'price': r.get('price', 0), 'change_pct': r.get('change_pct', 0),
            'pattern': r.get('pattern', '震荡'), 'confidence': r.get('confidence', 50),
            'reasons': r.get('reasons', []),
            'verified': r.get('verified', False), 'correct': r.get('correct'),
            'next_dir': nd.get('direction'), 'next_dir_conf': nd.get('confidence', 0),
            'gap_pct': r.get('gap_pct', 0),
        })

    return jsonify({'results': results, 'updated': intraday.get('predicted_at', ''), 'status': 'ready'})


@app.route('/api/scan/patterns', methods=['POST'])
def scan_patterns_api():
    """扫描自选股，识别技术形态/选股模式"""
    wl = load_watchlist()
    if not wl:
        return jsonify({'patterns': [], 'message': '自选股列表为空'})

    import concurrent.futures

    def fetch_with_code(s):
        full = s['market'] + s['code']
        try:
            k = fetch_kline(full, 120)
            return s['code'], s['market'], s.get('name', s['code']), k
        except:
            return s['code'], s['market'], s.get('name', s['code']), []

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as exe:
        kline_results = list(exe.map(fetch_with_code, wl))

    # 构建 klines_all dict
    klines_all = {}
    code_info = {}
    for code, market, name, k in kline_results:
        if len(k) >= 60:
            klines_all[f'{market}{code}'] = k
            code_info[f'{market}{code}'] = {'code': code, 'market': market, 'name': name}

    raw = scan_patterns(klines_all)

    # 格式化输出
    patterns_out = []
    for full_code, matches in raw.items():
        info = code_info.get(full_code, {})
        for m in matches:
            patterns_out.append({
                'code': info.get('code', full_code),
                'market': info.get('market', 'sh'),
                'name': info.get('name', full_code),
                'pattern_key': m['key'],
                'pattern_name': m['name'],
                'label': m['info'].get('label', ''),
                'detail': {k: v for k, v in m['info'].items() if k != 'label'},
            })

    # 按模式名称分组
    return jsonify({
        'patterns': patterns_out,
        'count': len(patterns_out),
        'stocks_matched': len(raw),
    })


# 全市场股票列表缓存 (5分钟)
_STOCK_LIST_CACHE = {'time': 0, 'data': []}

def fetch_a_share_list():
    """获取全A股列表（优先用本地文件），排除创业板/科创板/ST"""
    now = time.time()
    if now - _STOCK_LIST_CACHE['time'] < 300 and _STOCK_LIST_CACHE['data']:
        return _STOCK_LIST_CACHE['data']

    # 优先用本地保存的 all_stocks.json（5512只）
    local_file = os.path.join(DATA_DIR, 'all_stocks.json')
    if os.path.exists(local_file):
        try:
            with open(local_file, 'r', encoding='utf-8') as f:
                all_stocks = json.load(f)
            stocks = []
            for s in all_stocks:
                code = str(s.get('code', ''))
                name = str(s.get('name', ''))
                if s.get('market') == 'bj': continue  # 排除北交所
                if code.startswith('3') or code.startswith('688'): continue
                if 'ST' in name.upper() or '*' in name.upper(): continue
                market = 'sh' if code.startswith('6') else 'sz'
                stocks.append({'code': code, 'market': market, 'name': name,
                               'price': float(s.get('price', 10) or 10),
                               'volume': int(s.get('volume', 0) or 0),
                               'change_pct': float(s.get('change_pct', 0) or 0),
                               'pe': float(s.get('pe', 0) or 0)})
            if len(stocks) >= 1000:
                _STOCK_LIST_CACHE['time'] = now
                _STOCK_LIST_CACHE['data'] = stocks
                print(f"  [fetch_a_share_list] loaded {len(stocks)} stocks from local file")
                return stocks
        except Exception as e:
            print(f"  [fetch_a_share_list] local file error: {e}")

    # 本地文件不可用时从API获取
    url = 'http://push2.eastmoney.com/api/qt/clist/get'
    params = {
        'pn': 1, 'pz': 10000, 'po': 1, 'np': 1,
        'fltt': 2, 'invt': 2, 'fid': 'f3',
        'fs': 'm:0+t:6,m:0+t:13,m:1+t:2,m:1+t:23',
        'fields': 'f12,f14,f2,f3,f5,f9,f20'
    }
    import requests as req
    try:
        r = req.get(url, params=params, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
        data = r.json()
        items = data.get('data', {}).get('diff', [])
    except:
        items = []

    stocks = []
    for item in items:
        code = str(item.get('f12', ''))
        name = str(item.get('f14', ''))
        price = item.get('f2')
        if price is None: continue
        price = float(price)
        volume = item.get('f5', 0) or 0
        if price <= 0 or volume <= 0: continue
        if code.startswith('3') or code.startswith('688'): continue
        if 'ST' in name.upper() or '*' in name.upper(): continue
        if price < 2 or price > 200: continue
        change_pct = item.get('f3', 0) or 0
        pe = item.get('f9', 0) or 0
        market = 'sh' if code.startswith('6') else 'sz'
        stocks.append({'code': code, 'market': market, 'name': name,
                       'price': price, 'volume': volume, 'change_pct': change_pct, 'pe': pe})

    if len(stocks) < 500:
        stocks = [{"code":s[0],"market":s[1],"name":s[2],"price":10,"volume":1000000,"change_pct":0,"pe":0} for s in STATIC_STOCKS]

    _STOCK_LIST_CACHE['time'] = now
    _STOCK_LIST_CACHE['data'] = stocks
    return stocks


@app.route('/api/scan/market', methods=['POST'])
def scan_market_api():
    """全市场形态扫描 - 排除创业板/科创板/ST"""
    stocks = fetch_a_share_list()
    if not stocks:
        return jsonify({'error': '获取股票列表失败', 'patterns': []}), 500

    total = len(stocks)
    # 按成交量排序，取前200只最活跃的，排除涨停/涨幅过大的
    stocks.sort(key=lambda x: abs(x.get('volume', 0)), reverse=True)
    candidates = [s for s in stocks[:500] if (s.get('change_pct', 0) or 0) < 7 and (s.get('pe', 0) or 0) >= 0][:500]

    import concurrent.futures
    def fetch_kline_for_stock(s):
        try:
            k = fetch_kline(s['market'] + s['code'], 120)
            return s['code'], s['market'], s['name'], k
        except:
            return s['code'], s['market'], s['name'], []

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as exe:
        kline_results = list(exe.map(fetch_kline_for_stock, candidates))

    klines_all = {}
    code_info = {}
    for code, market, name, k in kline_results:
        if len(k) >= 60:
            klines_all[f'{market}{code}'] = k
            code_info[f'{market}{code}'] = {'code': code, 'market': market, 'name': name}

    candidate_lookup = {s['code']: s for s in candidates}
    # real-time quote from Tencent for accurate change_pct
    qcodes = ','.join([s['market'] + s['code'] for s in candidates[:500]])
    if qcodes:
        try:
            import requests as _rq
            _qr = _rq.get('https://qt.gtimg.cn/q=' + qcodes, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
            _qr.encoding = 'gbk'
            for _ql in _qr.text.split(chr(10)):
                import re as _re
                _qm = _re.search('v_[a-z]+\\d+="(.+)"', _ql)
                if not _qm: continue
                _qf = _qm.group(1).split('~')
                if len(_qf) < 40: continue
                _qc = _qf[2]
                if _qc in candidate_lookup:
                    try:
                        candidate_lookup[_qc]['change_pct'] = float(_qf[32]) if _qf[32] else 0
                    except Exception as e:
                        print(f'[market_scan] 解析涨跌幅失败 {_qc}: {e}')
                    try:
                        pe_val = float(_qf[39]) if len(_qf) > 39 and _qf[39] else 0
                        candidate_lookup[_qc]['pe'] = pe_val
                    except Exception as e:
                        print(f'[market_scan] 解析PE失败 {_qc}: {e}')
        except Exception as e:
            print(f'[market_scan] 批量行情失败: {e}')


    raw = scan_patterns(klines_all)
    patterns_out = []
    for full_code, matches in raw.items():
        info = code_info.get(full_code, {})
        cand = candidate_lookup.get(info.get('code', ''), {})
        chg = cand.get('change_pct', 0) or 0
        risk = ''
        if chg >= 9.5: risk = '涨停'
        elif chg >= 7: risk = '涨幅过大'
        for m in matches:
            patterns_out.append({
                'code': info.get('code', full_code),
                'market': info.get('market', 'sh'),
                'name': info.get('name', full_code),
                'pattern_key': m['key'],
                'pattern_name': m['name'],
                'label': m['info'].get('label', ''),
                'risk': risk,
                'change_pct': round(chg, 2),
                'detail': {k: v for k, v in m['info'].items() if k != 'label'},
            })

    return jsonify({
        'patterns': patterns_out,
        'count': len(patterns_out),
        'stocks_matched': len(raw),
        'total_scanned': total,
        'candidates': len(candidates),
    })


@app.route('/api/scan/weekly')
def scan_weekly_api():
    """全市场周线扫描"""
    stocks = fetch_a_share_list()
    if not stocks:
        return jsonify({'patterns': [], 'count': 0})
    candidates = [s for s in stocks if (s.get('change_pct', 0) or 0) < 9.5 and (s.get('pe', 0) or 0) >= 0]
    candidates.sort(key=lambda x: abs(x.get('volume', 0) or 0), reverse=True)
    candidates = candidates[:500]

    import concurrent.futures
    def fetch_wk(s):
        try:
            k = fetch_kline(s['market'] + s['code'], 30, period='week')
            return s, k
        except:
            return s, []
    wk_map = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as exe:
        for s, k in exe.map(fetch_wk, candidates):
            if len(k) >= 8:
                wk_map[s['code']] = {'info': s, 'kline': k}

    from engine.weekly import assess_weekly
    patterns_out = []
    for code, item in wk_map.items():
        try:
            s = item['info']
            r = assess_weekly(item['kline'])
            if r['score'] >= 50:
                chg = s.get('change_pct', 0) or 0
                risk = '涨停' if chg >= 9.5 else '涨幅过大' if chg >= 7 else ''
                patterns_out.append({
                    'code': code, 'market': s['market'], 'name': s.get('name', code),
                    'pattern_key': 'weekly_bullish', 'pattern_name': '周线多头',
                    'label': r['summary'], 'risk': risk,
                    'change_pct': round(chg, 2),
                    'detail': r['signals'],
                })
                if r['signals'].get('engulfing', {}).get('engulfing'):
                    patterns_out.append({
                        'code': code, 'market': s['market'], 'name': s.get('name', code),
                        'pattern_key': 'weekly_engulfing', 'pattern_name': '周线阳包阴',
                        'label': '上周阴被本周阳包掉', 'risk': risk,
                        'change_pct': round(chg, 2), 'detail': {},
                    })
                if r['signals'].get('ma_converge_spread', {}).get('converge_spread'):
                    cs = r['signals']['ma_converge_spread']
                    patterns_out.append({
                        'code': code, 'market': s['market'], 'name': s.get('name', code),
                        'pattern_key': 'weekly_converge_spread', 'pattern_name': '周线粘合向上发散',
                        'label': f'MA5:{cs["ma5"]} MA10:{cs["ma10"]} MA20:{cs["ma20"]}', 'risk': risk,
                        'change_pct': round(chg, 2), 'detail': {},
                    })
                if r['signals'].get('macd', {}).get('golden_cross'):
                    patterns_out.append({
                        'code': code, 'market': s['market'], 'name': s.get('name', code),
                        'pattern_key': 'weekly_macd_gc', 'pattern_name': '周线金叉',
                        'label': 'MACD周线金叉', 'risk': risk,
                        'change_pct': round(chg, 2), 'detail': {},
                    })
                if r['signals'].get('macd', {}).get('second_gc'):
                    patterns_out.append({
                        'code': code, 'market': s['market'], 'name': s.get('name', code),
                        'pattern_key': 'weekly_macd_sgc', 'pattern_name': '周线二次金叉',
                        'label': 'MACD零轴上方二次金叉', 'risk': risk,
                        'change_pct': round(chg, 2), 'detail': {},
                    })
                if r['signals'].get('rsi_divergence', {}).get('divergence'):
                    patterns_out.append({
                        'code': code, 'market': s['market'], 'name': s.get('name', code),
                        'pattern_key': 'weekly_divergence', 'pattern_name': '周线底背离',
                        'label': 'RSI底背离', 'risk': risk,
                        'change_pct': round(chg, 2), 'detail': {},
                    })
                if r['signals'].get('volume_stack', {}).get('spike'):
                    patterns_out.append({
                        'code': code, 'market': s['market'], 'name': s.get('name', code),
                        'pattern_key': 'weekly_spike', 'pattern_name': '周线放量突破',
                        'label': f"周量{r['signals']['volume_stack']['ratio']}倍", 'risk': risk,
                        'change_pct': round(chg, 2), 'detail': {},
                    })
        except:
            pass

    return jsonify({'patterns': patterns_out, 'count': len(patterns_out), 'stocks_matched': len(wk_map), 'total_scanned': len(candidates)})



@app.route('/api/stock/<code>/plunge')
def stock_plunge_api(code):
    """下跌超3%原因分析"""
    market = request.args.get('market', 'sh')
    full_code = market + code

    reasons = []

    # 1. 获取基础数据
    kline = fetch_kline(full_code, 120)
    if not kline or len(kline) < 20:
        return jsonify({'code': code, 'reasons': [], 'summary': '数据不足'})

    closes = [k['close'] for k in kline]
    cur_price = closes[-1]
    change_pct = (closes[-1] - closes[-2]) / closes[-2] * 100 if len(closes) >= 2 else 0

    # 2. 新闻分析
    try:
        news = fetch_news(code, market)
        if news:
            neg_news = [n for n in news if analyze_sentiment([n])[0] < -0.2]
            for n in neg_news[:3]:
                reasons.append({'dim': 'news', 'label': '利空消息', 'detail': n.get('title', '')})
    except:
        pass

    # 3. 板块表现
    try:
        snap_path = os.path.join(DATA_DIR, 'snapshots', 'sectors.json')
        if os.path.exists(snap_path):
            sectors = json.load(open(snap_path)).get('sectors', [])
            for sec in sectors:
                for stk in sec.get('stocks', []):
                    if stk.get('code') == code and stk.get('market') == market:
                        up = sec.get('up_count', 0)
                        down = sec.get('down_count', 0)
                        total = up + down
                        if total > 0 and down / total > 0.6:
                            reasons.append({'dim': 'sector', 'label': '板块拖累', 'detail': f'{sec.get("name","")}板块跌多涨少({down}/{total})'})
                        break
    except:
        pass

    # 4. 相关商品期货
    try:
        name_hint = ''
        # Try to get stock name from quote
        q = fetch_tencent_quote(full_code)
        if q and q.get(code):
            name_hint = q[code].get('name', '')
        if not name_hint:
            wl = load_watchlist()
            for s in wl:
                if s['code'] == code: name_hint = s.get('name', ''); break

        keywords = {'铜':'沪铜伦铜COMEX铜', '铝':'沪铝伦铝', '锌':'沪锌伦锌', '镍':'沪镍伦镍',
                    '铅':'沪铅伦铅', '锡':'沪锡伦锡', '金':'沪金COMEX黄金', '银':'沪银COMEX白银',
                    '原油':'原油WTI原油', '油':'原油', '钢':'螺纹钢', '铁':'铁矿石'}
        matched = []
        for kw, futures_list in keywords.items():
            if kw in name_hint:
                matched.append(futures_list)
        if matched:
            reasons.append({'dim': 'futures', 'label': '商品期货', 'detail': '相关品种：' + '、'.join(matched) + '，具体涨跌需查看宏观商品页'})
    except:
        pass

    # 5. 量价分析
    try:
        if len(kline) >= 20:
            avg_vol = sum(k['volume'] for k in kline[-20:]) / 20
            last_vol = kline[-1]['volume']
            vol_ratio = last_vol / avg_vol if avg_vol > 0 else 1
            if vol_ratio > 1.5:
                reasons.append({'dim': 'volume', 'label': '放量杀跌', 'detail': f'今日量比{vol_ratio:.1f}倍，放量下跌'})
            elif vol_ratio < 0.6:
                reasons.append({'dim': 'volume', 'label': '缩量下跌', 'detail': f'今日量比{vol_ratio:.1f}倍，缩量下跌（抛压不大）'})
    except:
        pass

    # 6. 技术破位
    try:
        from engine.indicators import calc_support_resistance
        sr = calc_support_resistance(kline)
        if sr:
            nearest_support = sr.get('nearest_support', 0)
            if nearest_support > 0 and cur_price < nearest_support:
                reasons.append({'dim': 'technical', 'label': '破位下跌', 'detail': f'跌破支撑{nearest_support:.2f}'})
        # 均线破位
        if len(closes) >= 60:
            ma60 = sum(closes[-60:]) / 60
            if closes[-2] > ma60 > cur_price:
                reasons.append({'dim': 'technical', 'label': '破位下跌', 'detail': f'跌破MA60均线({ma60:.2f})'})
    except:
        pass

    # 去重
    seen = set()
    unique = []
    for r in reasons:
        key = r['detail']
        if key not in seen:
            seen.add(key)
            unique.append(r)

    # 生成摘要
    dim_names = {'news':'利空','sector':'板块','futures':'商品','volume':'量价','capital':'资金','technical':'破位'}
    summary_parts = [dim_names.get(r['dim'], r['dim']) for r in unique[:3]]
    summary = '叠加'.join(summary_parts) if summary_parts else (f'下跌{abs(change_pct):.1f}%，无明显异常信号' if change_pct else '')

    return jsonify({'code': code, 'market': market, 'change_pct': round(change_pct, 2),
                    'reasons': unique, 'summary': summary or ''})


@app.route('/api/system/status')
def system_status_api():
    """系统状态及已部署功能"""
    from engine.weight_optimizer import get_weight_summary
    from engine.ml_scorer import is_ready, MODEL_FILE, FEATURE_FILE
    import os
    ml_ready = is_ready()
    ml_time = ''
    if ml_ready and os.path.exists(FEATURE_FILE):
        try:
            import json
            with open(FEATURE_FILE) as f:
                ml_time = json.load(f).get('trained_at', '')
        except: pass
    weight_info = get_weight_summary()
    has_closing = os.path.exists(os.path.join(os.path.dirname(__file__), 'data', 'closing'))
    features = []
    if ml_ready: features.append(f'ML评分({ml_time})')
    if '动态' in weight_info: features.append('动态权重')
    features.append('周线分析')
    features.append('量价四形态')
    features.append('主力控盘度')
    features.append('尾盘监控')
    features.append('下跌原因分析')
    return jsonify({
        'status': 'running',
        'version': '3.0',
        'features': features,
        'message': ' | '.join(features),
        'ml_ready': ml_ready,
        'ml_trained_at': ml_time,
        'weight_mode': '动态' if '动态' in weight_info else '固定',
    })
CLOSING_DIR = os.path.join(DATA_DIR, 'closing')
CLOSING_BASELINE = os.path.join(CLOSING_DIR, 'baseline.json')

def _save_closing_baseline():
    """14:15 快照股价基准"""
    stocks = fetch_a_share_list()
    if not stocks: return
    candidates = [s for s in stocks if (s.get('change_pct', 0) or 0) < 9.5 and (s.get('pe', 0) or 0) >= 0]
    candidates.sort(key=lambda x: abs(x.get('volume', 0) or 0), reverse=True)
    candidates = candidates[:500]
    codes_str = ','.join([s['market'] + s['code'] for s in candidates])
    quotes = fetch_tencent_quote(codes_str) if codes_str else {}
    baseline = {}
    for s in candidates:
        q = quotes.get(s['code'], {})
        p = q.get('price', 0)
        if p > 0:
            baseline[s['code']] = {'name': s.get('name', s['code']), 'market': s['market'], 'price': p, 'snap_time': time.strftime('%H:%M:%S')}
    os.makedirs(CLOSING_DIR, exist_ok=True)
    with open(CLOSING_BASELINE, 'w', encoding='utf-8') as f:
        json.dump({'time': time.strftime('%Y-%m-%d %H:%M:%S'), 'baseline': baseline}, f)
    print(f'[closing] 基准快照: {len(baseline)} 只')

def _load_closing_baseline():
    if not os.path.exists(CLOSING_BASELINE): return None
    with open(CLOSING_BASELINE, 'r', encoding='utf-8') as f:
        return json.load(f)

@app.route('/api/scan/closing')
def closing_scan_api():
    """尾盘拉抬监控"""
    force = request.args.get('force', '0') == '1'
    now = time.localtime()
    hm = now.tm_hour * 60 + now.tm_min
    today = time.strftime('%Y-%m-%d')
    start_hm = 14 * 60 + 15
    end_hm = 15 * 60

    if hm < start_hm and not force:
        return jsonify({'status': 'waiting', 'message': f'尾盘监控(14:15-15:00) 当前{now.tm_hour}:{now.tm_min:02d}'})

    # 首次调用时快照
    baseline_data = _load_closing_baseline()
    if force or not baseline_data or baseline_data.get('time', '').split(' ')[0] != today:
        _save_closing_baseline()
        baseline_data = _load_closing_baseline()
        if not baseline_data:
            return jsonify({'status': 'error', 'message': '基准快照失败'})
        return jsonify({'status': 'baseline', 'message': '基准已采集，下次刷新开始监控'})

    baseline = baseline_data.get('baseline', {})
    codes_str = ','.join([f"{v['market']}{k}" for k, v in baseline.items()])
    quotes = fetch_tencent_quote(codes_str) if codes_str else {}

    spikes = []
    for code, b in baseline.items():
        q = quotes.get(code, {})
        cur = q.get('price', 0)
        if cur <= 0: continue
        spike_pct = (cur - b['price']) / b['price'] * 100
        if 1 < spike_pct <= 5:
            spikes.append({
                'code': code, 'name': b.get('name', code),
                'price': round(cur, 2), 'spike_pct': round(spike_pct, 2),
                'base_price': round(b['price'], 2),
            })

    # 读取已有记录，去重累积
    today_file = os.path.join(CLOSING_DIR, f'spikes_{today}.json')
    all_spikes = []
    if os.path.exists(today_file):
        try:
            with open(today_file, 'r', encoding='utf-8') as f:
                all_spikes = json.load(f)
        except:
            all_spikes = []
    exist_codes = set(s['code'] for s in all_spikes)
    for s in spikes:
        if s['code'] not in exist_codes:
            all_spikes.append(s)
            exist_codes.add(s['code'])

    if spikes:
        os.makedirs(CLOSING_DIR, exist_ok=True)
        with open(today_file, 'w', encoding='utf-8') as f:
            json.dump(all_spikes, f, ensure_ascii=False, indent=2)

    if hm > end_hm:
        return jsonify({'status': 'done', 'time': time.strftime('%H:%M:%S'), 'date': today,
                        'spikes': all_spikes, 'message': f'收盘，共{len(all_spikes)}只尾盘拉抬'})

    return jsonify({'status': 'active', 'time': time.strftime('%H:%M:%S'), 'date': today,
                    'spikes': all_spikes})

@app.route('/api/closing/history')
def closing_history_api():
    """尾盘拉抬历史"""
    date = request.args.get('date', '')
    if not date:
        # 默认返回最近2天
        today = time.strftime('%Y-%m-%d')
        from datetime import timedelta
        try:
            td = time.localtime()
            d1 = time.strftime('%Y-%m-%d', td)
            d2 = time.strftime('%Y-%m-%d', time.localtime(time.mktime(td) - 86400))
            dates = [d1, d2]
        except:
            dates = [today]
    else:
        dates = [date]
    result = {}
    for d in dates:
        fp = os.path.join(CLOSING_DIR, f'spikes_{d}.json')
        if os.path.exists(fp):
            with open(fp, 'r', encoding='utf-8') as f:
                result[d] = json.load(f)
    return jsonify(result)



@app.route('/api/dailypick')
def dailypick_api():
    """返回每日一股推荐结果"""
    period, valid_from, valid_until = get_dailypick_period()
    cached = None
    if os.path.exists(DAILYPICK_FILE):
        try:
            with open(DAILYPICK_FILE, 'r', encoding='utf-8') as f:
                cached = json.load(f)
        except:
            pass
    if cached and cached.get('status') == 'ready' and cached.get('period') == period:
        return jsonify({
            'status': 'ready', 'period': period,
            'valid_from': valid_from, 'valid_until': valid_until,
            'picks': cached.get('picks', [cached['pick']] if cached.get('pick') else []), 'computed_at': cached.get('computed_at'),
            'scan_summary': cached.get('scan_summary', {}),
        })
    return jsonify({
        'status': 'no_data', 'period': period,
        'valid_from': valid_from, 'valid_until': valid_until,
    })


# =================== 导出功能 ===================

@app.route('/api/export/scan')
def export_scan():
    """导出自选股扫描结果为 CSV"""
    wl = load_watchlist()
    if not wl:
        return '自选股列表为空', 400

    codes_str = ','.join([s['market'] + s['code'] for s in wl])
    quotes = fetch_tencent_quote(codes_str)

    import io
    import csv
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['代码', '名称', '最新价', '涨跌幅%', '涨跌额', '市盈率', '评分', '建议'])

    for s in wl:
        q = quotes.get(s['code'], {})
        score = 50
        advice = '持有'
        pe = abs(q.get('pe', 0) or 0)
        if 0 < pe < 20: score += 10
        elif pe > 50: score -= 10
        if q.get('changePercent', 0) > 0: score += 5
        else: score -= 5
        score = max(0, min(100, score))
        if score >= 65: advice = '买入'
        elif score <= 35: advice = '卖出'
        else: advice = '持有'

        writer.writerow([
            s['code'],
            q.get('name', s.get('name', s['code'])),
            q.get('price', 0),
            q.get('changePercent', 0),
            q.get('change', 0),
            q.get('pe', 0),
            score,
            advice,
        ])

    csv_bytes = output.getvalue()
    output.close()
    return Response(
        csv_bytes.encode('utf-8-sig'),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=scan_results.csv'}
    )


@app.route('/api/export/market')
def export_market():
    """导出全市场形态扫描结果为 CSV"""
    stocks = fetch_a_share_list()
    if not stocks:
        return '获取股票列表失败', 500

    total = len(stocks)
    stocks.sort(key=lambda x: abs(x.get('volume', 0)), reverse=True)
    candidates = [s for s in stocks[:500] if (s.get('change_pct', 0) or 0) < 7 and (s.get('pe', 0) or 0) >= 0][:500]

    import concurrent.futures
    def fetch_kline_for_stock(s):
        try:
            k = fetch_kline(s['market'] + s['code'], 120)
            return s['code'], s['market'], s['name'], k
        except:
            return s['code'], s['market'], s['name'], []

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as exe:
        kline_results = list(exe.map(fetch_kline_for_stock, candidates))

    klines_all = {}
    code_info = {}
    for code, market, name, k in kline_results:
        if len(k) >= 60:
            klines_all[f'{market}{code}'] = k
            code_info[f'{market}{code}'] = {'code': code, 'market': market, 'name': name}

    raw = scan_patterns(klines_all)

    candidate_lookup = {s['code']: s for s in candidates}
    qcodes = ','.join([s['market'] + s['code'] for s in candidates[:50]])
    if qcodes:
        try:
            import requests as _rq
            _qr = _rq.get('https://qt.gtimg.cn/q=' + qcodes, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
            _qr.encoding = 'gbk'
            for _ql in _qr.text.split(chr(10)):
                _qm = __import__('re').search('v_[a-z]+\\d+="(.+)"', _ql)
                if not _qm: continue
                _qf = _qm.group(1).split('~')
                if len(_qf) < 40: continue
                _qc = _qf[2]
                if _qc in candidate_lookup:
                    try:
                        candidate_lookup[_qc]['change_pct'] = float(_qf[32]) if _qf[32] else 0
                    except: pass
        except: pass

    import io, csv
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['代码', '市场', '名称', '模式', '标签', '涨跌幅%', '风险'])

    for full_code, matches in raw.items():
        info = code_info.get(full_code, {})
        cand = candidate_lookup.get(info.get('code', ''), {})
        chg = cand.get('change_pct', 0) or 0
        risk = ''
        if chg >= 9.5: risk = '涨停'
        elif chg >= 7: risk = '涨幅过大'
        for m in matches:
            writer.writerow([
                info.get('code', full_code),
                info.get('market', 'sh'),
                info.get('name', full_code),
                m['name'],
                m['info'].get('label', ''),
                round(chg, 2),
                risk,
            ])

    csv_bytes = output.getvalue()
    output.close()
    return Response(
        csv_bytes.encode('utf-8-sig'),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=market_scan_results.csv'}
    )


@app.route('/api/export/patterns')
def export_patterns():
    """导出形态扫描结果为 CSV"""
    wl = load_watchlist()
    if not wl:
        return '自选股列表为空', 400

    import concurrent.futures
    def fetch_with_code(s):
        full = s['market'] + s['code']
        try:
            k = fetch_kline(full, 120)
            return s['code'], s['market'], s.get('name', s['code']), k
        except:
            return s['code'], s['market'], s.get('name', s['code']), []

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as exe:
        kline_results = list(exe.map(fetch_with_code, wl))

    klines_all = {}
    code_info = {}
    for code, market, name, k in kline_results:
        if len(k) >= 60:
            klines_all[f'{market}{code}'] = k
            code_info[f'{market}{code}'] = {'code': code, 'market': market, 'name': name}

    raw = scan_patterns(klines_all)

    import io, csv
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['代码', '市场', '名称', '模式', '标签'])

    for full_code, matches in raw.items():
        info = code_info.get(full_code, {})
        for m in matches:
            writer.writerow([
                info.get('code', full_code),
                info.get('market', 'sh'),
                info.get('name', full_code),
                m['name'],
                m['info'].get('label', ''),
            ])

    csv_bytes = output.getvalue()
    output.close()
    return Response(
        csv_bytes.encode('utf-8-sig'),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=pattern_results.csv'}
    )


@app.route('/dl/csv')
def dl_csv_page():
    """以HTML页面显示CSV内容，方便手机复制"""
    import urllib.parse
    text = "代码,名称,价格\n000001,测试股票,10.50\n"
    html = f'''<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>选股结果CSV</title><style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:sans-serif;background:#0f0f23;color:#e0e0e0;padding:16px}}
h2{{font-size:16px;margin-bottom:10px;color:#00d2ff}}
textarea{{width:100%;height:300px;background:#1a1a3e;color:#e0e0e0;border:1px solid rgba(255,255,255,.1);border-radius:8px;padding:12px;font-size:13px;font-family:monospace;resize:vertical}}
.btn{{display:block;width:100%;padding:14px;border:none;border-radius:8px;font-size:16px;font-weight:600;cursor:pointer;text-align:center;margin:10px 0}}
.btn-green{{background:#2ed573;color:#fff}}
.btn-blue{{background:linear-gradient(135deg,#00d2ff,#3a7bd5);color:#fff}}
.hint{{font-size:12px;color:#888;text-align:center;margin-top:8px}}
</style></head><body>
<h2>📋 选股结果</h2>
<p style="font-size:12px;color:#888;margin-bottom:8px">点击textarea全选 → 复制 → 粘贴到WPS/Excel</p>
<textarea id="csv" readonly onclick="this.select();document.getElementById('tip').textContent='已全选，请复制'">{text}</textarea>
<button class="btn btn-green" onclick="var t=document.getElementById('csv');t.select();document.execCommand('copy');this.textContent='✅ 已复制!'">📋 一键复制</button>
<p id="tip" class="hint">点击上方按钮或长按文本框复制内容</p>
</body></html>'''
    return Response(html, mimetype='text/html;charset=utf-8')


# =================== 启动 ===================

import threading

# ─── 定时扫描 ───
SNAPSHOT_DIR = os.path.join(DATA_DIR, 'snapshots')
# 15分钟间隔记录时间点: 09:25~11:25 上午, 13:10~15:10 下午
RECORD_TIMES_15MIN = [
    (9,25),(9,40),(9,55),(10,10),(10,25),(10,40),(10,55),(11,10),(11,25),
    (13,10),(13,25),(13,40),(13,55),(14,10),(14,25),(14,40),(14,55),(15,10),
]
SCHEDULE_TIMES = RECORD_TIMES_15MIN + [(15, 1)]  # 15:01 触发明日推荐计算
_DAILY_PICK_LOCK = threading.Lock()

# ─── 每日一股 ───
DAILYPICK_FILE = os.path.join(DATA_DIR, 'dailypick.json')
INTRADAY_FILE = os.path.join(DATA_DIR, 'predictions', 'intraday.json')

def predict_intraday(watchlist, quotes):
    """09:25 开盘后预测今日走势形态"""
    today = time.strftime('%Y-%m-%d')
    from engine.indicators import calc_support_resistance
    from engine.patterns import scan_patterns

    results = []
    for s in watchlist:
        try:
            code, market = s['code'], s['market']
            q = quotes.get(code, {})
            price = q.get('price', 0)
            if price <= 0:
                continue
            yesterday = q.get('yesterdayClose', price)
            day_open = q.get('open', price)
            gap_pct = round((day_open - yesterday) / yesterday * 100, 2) if yesterday else 0
            change_pct = round((price - yesterday) / yesterday * 100, 2) if yesterday else 0

            k = fetch_kline(market + code, 120)
            if len(k) < 60:
                continue
            closes = [x['close'] for x in k]
            sr = calc_support_resistance(k)
            pats = scan_patterns({market + code: k})
            patterns = pats.get(market + code, [])
            decision = make_decision(closes, k, patterns, sr, None, q, code=code, market=market)

            sig = decision.get('signal', '持有')
            sc = decision.get('score', 50)
            details = decision.get('details', {})
            trend_score = details.get('trend', {}).get('score', 50)
            capital_score = details.get('capital', {}).get('score', 50)
            intraday_score = details.get('intraday', {}).get('score', 50)

            pattern = '震荡'
            confidence = 50
            reasons = []

            if gap_pct > 1:
                reasons.append(f'高开{gap_pct}%')
                if sig in ('买入', '增持'):
                    pattern = '一直涨'
                    confidence = min(95, int(sc * 1.2))
                    reasons.append(f'信号{sig}({sc}分)')
                else:
                    pattern = '先涨后跌'
                    confidence = min(85, int(sc + 30))
                    reasons.append(f'信号{sig}')
            elif gap_pct < -1:
                reasons.append(f'低开{gap_pct}%')
                if sig in ('买入', '增持'):
                    pattern = '先跌后涨'
                    confidence = min(90, int(sc + 10))
                    reasons.append(f'信号{sig}({sc}分)')
                else:
                    pattern = '一直跌'
                    confidence = min(90, int(sc * 1.3))
                    reasons.append(f'信号{sig}')
            else:
                reasons.append(f'平开{gap_pct}%')
                if trend_score > 60 and capital_score > 60:
                    pattern = '一直涨'
                    confidence = min(80, int((trend_score + capital_score) / 2))
                    reasons.append(f'趋势↑({trend_score})资金↑({capital_score})')
                elif trend_score < 40 and capital_score < 40:
                    pattern = '一直跌'
                    confidence = min(80, int(100 - (trend_score + capital_score) / 2))
                    reasons.append(f'趋势↓({trend_score})资金↓({capital_score})')
                elif trend_score > 50 and intraday_score > 50:
                    pattern = '先跌后涨'
                    confidence = 65
                    reasons.append(f'趋势偏多({trend_score})')
                elif trend_score < 50 and intraday_score < 50:
                    pattern = '先涨后跌'
                    confidence = 65
                    reasons.append(f'趋势偏空({trend_score})')

            results.append({
                'code': code, 'market': market, 'name': s.get('name', code),
                'price': price, 'change_pct': change_pct,
                'pattern': pattern, 'confidence': int(confidence),
                'reasons': reasons, 'gap_pct': gap_pct,
                'signal': sig, 'score': sc,
                'verified': False, 'correct': None,
            })
        except:
            pass

    payload = {'date': today, 'predicted_at': time.strftime('%H:%M:%S'), 'results': results}
    os.makedirs(os.path.dirname(INTRADAY_FILE), exist_ok=True)
    with open(INTRADAY_FILE, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False)
    print(f'[intraday] 预测完成: {len(results)} 只')
    return results

def verify_intraday():
    """15:01 验证今日开盘预测"""
    today = time.strftime('%Y-%m-%d')
    if not os.path.exists(INTRADAY_FILE):
        return 0
    try:
        with open(INTRADAY_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except:
        return 0
    if data.get('date') != today:
        return 0

    verified = 0
    for r in data.get('results', []):
        if r.get('verified'):
            continue
        code, market = r['code'], r.get('market', 'sh')
        try:
            klines = fetch_kline(market + code, 5)
            if not klines or len(klines) < 2:
                continue
            today_k = None
            for k in klines:
                if k['date'] == today:
                    today_k = k
                    break
            if not today_k:
                continue
            day_open = today_k['open']
            day_close = today_k['close']
            day_high = today_k['high']
            day_low = today_k['low']
            amplitude = (day_high - day_low) / day_low * 100 if day_low else 0

            if day_close > day_open and amplitude > 1.5:
                actual = '一直涨'
            elif day_close < day_open and amplitude > 1.5:
                actual = '一直跌'
            elif day_high - day_close > (day_close - day_open) * 1.5:
                actual = '先涨后跌'
            elif day_close - day_low > (day_open - day_close) * 1.5:
                actual = '先跌后涨'
            else:
                actual = '震荡'

            r['actual'] = actual
            r['verified'] = True
            r['correct'] = (r.get('pattern', '') == actual)
            verified += 1
        except:
            continue

    with open(INTRADAY_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)
    print(f'[intraday] 验证完成: {verified} 只')
    return verified

def get_dailypick_period():
    """根据当前时间返回 (period, valid_from, valid_until)"""
    now = time.localtime()
    hm = now.tm_hour * 60 + now.tm_min
    today = time.strftime('%Y-%m-%d')
    tomorrow_ts = time.mktime(now) + 86400
    tomorrow = time.strftime('%Y-%m-%d', time.localtime(tomorrow_ts))
    if hm < 9 * 60 + 25:
        return 'afternoon', today + ' 15:01', today + ' 09:25'
    elif hm < 15 * 60 + 1:
        return 'morning', today + ' 09:25', today + ' 15:01'
    else:
        return 'afternoon', today + ' 15:01', tomorrow + ' 09:25'

def compute_daily_pick(period='morning'):
    """全市场扫描，选出今日/明日推荐的一支最优股票"""
    if not _DAILY_PICK_LOCK.acquire(blocking=False):
        print('[dailypick] 计算中，跳过重复请求')
        return None
    try:
        print(f'[dailypick] 开始计算 {period} pick...')
        stocks = fetch_a_share_list()
        if not stocks:
            return None
        # 过滤涨停、ST、PE 负
        candidates = [s for s in stocks
                      if (s.get('change_pct', 0) or 0) < 9.0
                      and (s.get('pe', 0) or 0) >= 0]
        # 本地文件 volume 为 0，无法按活跃度排序 → 取代码中间段的股票（主流沪深主板）
        # 跳过 000xxx-002xxx（深圳主板）前段和 600xxx 前段，取 600200-600999、000400-001999 等区间
        if candidates and all(c.get('volume', 0) == 0 for c in candidates):
            import random
            random.shuffle(candidates)
            candidates = candidates[:500]  # 扩大到 500 只，优中选优
        else:
            candidates.sort(key=lambda x: abs(x.get('volume', 0) or 0), reverse=True)
            candidates = candidates[:500]
        print(f'[dailypick] 候选 {len(candidates)} 只，获取K线...')

        import concurrent.futures

        def fetch_kl(s):
            try:
                import signal
                # 限制单次K线获取 5 秒
                k = fetch_kline(s['market'] + s['code'], 120)
                return s, k
            except:
                return s, []
        kline_map = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as exe:
            for s, k in exe.map(fetch_kl, candidates):
                if len(k) >= 60:
                    kline_map[s['code']] = {'info': s, 'kline': k}
        print(f'[dailypick] K线就绪 {len(kline_map)} 只，获取实时行情...')

        # 批量获取实时行情（用于分时评分）
        quote_codes = ','.join(f'{v["info"]["market"]}{code}' for code, v in kline_map.items())
        quotes = fetch_tencent_quote(quote_codes) if quote_codes else {}

        print(f'[dailypick] 行情就绪，计算决策...')

        sector_list = []
        try:
            snap_path = os.path.join(DATA_DIR, 'snapshots', 'sectors.json')
            if os.path.exists(snap_path):
                sector_list = json.load(open(snap_path)).get('sectors', [])
        except:
            pass

        from engine.indicators import calc_support_resistance
        scored = []
        for code, item in kline_map.items():
            try:
                s = item['info']
                k = item['kline']
                closes = [x['close'] for x in k]
                sr = calc_support_resistance(k)
                sector_ctx = None
                for sec in sector_list:
                    for stk in sec.get('stocks', []):
                        if stk.get('code') == code and stk.get('market') == s['market']:
                            sector_ctx = {
                                'up_count': sec.get('up_count', 0),
                                'down_count': sec.get('down_count', 0),
                                'pattern_count': sec.get('pattern_count', 0),
                                'sector_name': sec.get('name', ''),
                            }
                            break
                    if sector_ctx:
                        break
                pats = scan_patterns({s['market'] + code: k})
                patterns = pats.get(s['market'] + code, [])
                pattern_names = [p['name'] for p in patterns]
                # 估值高与价格低背离检测（仅标签，不加分）
                try:
                    from engine.patterns import pattern_valuation_price_divergence
                    vpd_ok, vpd_info = pattern_valuation_price_divergence(k, pe=s.get('pe', 0))
                    if vpd_ok:
                        pattern_names.append('估值高与价格低背离')
                        patterns.append({'key': 'valuation_price_divergence', 'name': '估值高与价格低背离', 'info': vpd_info})
                except Exception as e:
                    print(f'[dailypick] {code} 估值标签检测失败: {e}')
                # 用最新收盘价作为价格
                cur_price = closes[-1] if closes else 0
                cur_chg = (closes[-1] / closes[-2] - 1) * 100 if len(closes) >= 2 else 0
                # 早期启动所需指标
                range_pos = 100
                vol_ratio = 1.0
                cum_3d_chg = 0
                try:
                    highs60 = [x['high'] for x in k[-60:]]
                    lows60 = [x['low'] for x in k[-60:]]
                    min60 = min(lows60); max60 = max(highs60)
                    range_pos = (cur_price - min60) / (max60 - min60) * 100 if max60 > min60 else 100
                    vols60 = [x['volume'] for x in k[-60:]]
                    avg60 = sum(vols60) / len(vols60)
                    vol_ratio = vols60[-1] / avg60 if avg60 > 0 else 1.0
                    if len(closes) >= 4:
                        cum_3d_chg = (closes[-1] - closes[-4]) / closes[-4] * 100
                    # 放量异动指标
                    vol_day_ratio = 0
                    is_green = False
                    if len(k) >= 2:
                        vol_day_ratio = k[-1]['volume'] / k[-2]['volume'] if k[-2]['volume'] > 0 else 0
                    if k:
                        is_green = k[-1]['close'] > k[-1]['open']
                except: pass
                q = quotes.get(code, {}) if isinstance(quotes, dict) else {}
                decision = make_decision(closes, k, patterns, sr, sector_ctx,
                                         quote=q, code=code, market=s['market'])
                # 筛选：排除涨停
                if cur_chg < 9.0:
                    agree = sum(1 for d in decision.get('details', {}).values()
                                if d.get('score', 0) >= 60)
                    # 周线加分
                    wk_bonus = 0
                    try:
                        wk = fetch_kline(s['market'] + code, 30, period='week')
                        if wk and len(wk) >= 4:
                            from engine.weekly import assess_weekly
                            wkr = assess_weekly(wk)
                            if wkr['score'] >= 60: wk_bonus = 10
                            elif wkr['score'] >= 50: wk_bonus = 5
                    except Exception as e:
                        print(f'[dailypick] {code} 周线加分失败: {e}')
                    vp_bonus = 0
                    try:
                        from engine.indicators import classify_vp_relationship
                        vpr = classify_vp_relationship(k, baseline=120, recent=20)
                        if vpr['type'] in ('量增价升',): vp_bonus = 8
                        elif vpr['type'] in ('量减价升',): vp_bonus = 3
                    except Exception as e:
                        print(f'[dailypick] {code} 量价加分失败: {e}')
                    # 横盘启动加分
                    cb_bonus = 0
                    try:
                        from engine.patterns import pattern_consolidation_breakout
                        cb_ok, cb_info = pattern_consolidation_breakout(k)
                        if cb_ok:
                            cb_bonus = 12 if cb_info.get('score', 0) >= 30 else 8
                    except Exception as e:
                        print(f'[dailypick] {code} 横盘启动加分失败: {e}')
                    # 跳空加分（集合竞价结果）
                    gap_bonus = 0
                    try:
                        if q:
                            op = q.get('open', 0)
                            yc = q.get('yesterdayClose', 0)
                            if op > 0 and yc > 0:
                                gap = (op - yc) / yc * 100
                                sig = decision.get('signal', '持有')
                                if gap > 1.5 and sig in ('买入', '增持'): gap_bonus = 8
                                elif gap < -1.5 and sig in ('卖出', '减仓'): gap_bonus = 8
                                elif gap > 1.5 and sig in ('卖出', '减仓'): gap_bonus = -5
                                elif gap < -1.5 and sig in ('买入', '增持'): gap_bonus = -5
                    except Exception as e:
                        print(f'[dailypick] {code} 跳空加分失败: {e}')
                    # 量价标签（预计算，避免后面取_kline为空）
                    _vp_label = ''
                    try:
                        from engine.indicators import classify_vp_relationship
                        _vpr = classify_vp_relationship(k, baseline=120, recent=20)
                        _vp_label = _vpr.get('label', '')
                    except:
                        pass
                    boosted = decision['score'] + wk_bonus + vp_bonus + cb_bonus + gap_bonus
                    scored.append({
                        'code': code, 'market': s['market'], 'name': s.get('name', code),
                        'price': cur_price, 'change_pct': round(cur_chg, 2),
                        'signal': decision['signal'], 'score': min(100, boosted),
                        'base_score': decision['score'],
                        'wk_bonus': wk_bonus, 'vp_bonus': vp_bonus, 'cb_bonus': cb_bonus, 'gap_bonus': gap_bonus,
                        'details': decision.get('details', {}),
                        'reasons': decision.get('reasons', []),
                        'patterns_found': pattern_names,
                        'method_agree': agree, 'total_methods': 6,
                        'sr': sr,
                        'vp_label': _vp_label,
                        'range_pos': round(range_pos, 1),
                        'vol_ratio': round(vol_ratio, 2),
                        'cum_3d_chg': round(cum_3d_chg, 2),
                        'vol_day_ratio': round(vol_day_ratio, 2),
                        'is_green': is_green,
                    })
            except:
                pass

        if not scored:
            print('[dailypick] 无符合条件的股票')
            return None

        # 排序: score 降序, 优先买入信号, method_agree 降序
        scored.sort(key=lambda r: (-r['score'], r['signal'] != '买入', -r['method_agree']))

        # 选前2名，确保没有接近涨停
        picks = []
        for b in scored:
            if len(picks) >= 2: break
            if b['change_pct'] < 8.5:
                picks.append(b)

        if not picks or picks[0]['score'] < 55:
            print(f'[dailypick] 最高分仅 {picks[0]["score"] if picks else 0}，不值得推荐')
            return None

        pick_list = []
        for i, best in enumerate(picks):
            pick = {
                'code': best['code'], 'market': best['market'], 'name': best['name'],
                'price': best['price'], 'change_pct': best['change_pct'],
                'signal': best['signal'], 'score': best['score'],
                'method_agree': best['method_agree'],
                'total_methods': best['total_methods'],
                'details': {},
                'top_reasons': best['reasons'][:5],
                'patterns_found': best['patterns_found'],
                'risk_warning': '',
                'sr': best['sr'],
            }
            for key, val in best['details'].items():
                s = val.get('score', 50)
                sig = '买入' if s >= 75 else '增持' if s >= 60 else '持有' if s >= 45 else '卖出'
                pick['details'][key] = {'score': s, 'signal': sig, 'reasons': val.get('reasons', [])}

            # 周线分析
            try:
                wk = fetch_kline(best['market'] + best['code'], 30, period='week')
                if wk and len(wk) >= 4:
                    from engine.weekly import assess_weekly
                    wr = assess_weekly(wk)
                    pick['weekly_signals'] = {
                        'score': wr['score'],
                        'summary': wr['summary'],
                        'ma20_up': wr['signals']['ma20_trend']['ma20_up'],
                        'consecutive_up': wr['signals']['consecutive_up']['consecutive_count'],
                    }
            except:
                pass

            # 量价标签
            if best.get('vp_label'):
                pick['vp'] = {'label': best['vp_label']}

            risk_parts = []
            if best['change_pct'] > 7:
                risk_parts.append(f'涨幅较大({best["change_pct"]}%)')
            if best['method_agree'] < 3:
                risk_parts.append('方法分歧较大')
            pick['risk_warning'] = ';'.join(risk_parts) if risk_parts else ''
            pick_list.append(pick)

        now_ts = time.time()
        if period == 'morning':
            valid_from = time.strftime('%Y-%m-%d') + ' 09:25'
            valid_until = time.strftime('%Y-%m-%d') + ' 15:01'
        else:
            valid_from = time.strftime('%Y-%m-%d') + ' 15:01'
            valid_until = time.strftime('%Y-%m-%d', time.localtime(now_ts + 86400)) + ' 09:25'

        # 统计横盘突破扫描结果
        cb_total = 0
        for b in scored:
            if b.get('cb_bonus', 0) >= 8:
                cb_total += 1
        # 横盘突破特别关注（从落选股中检出，作为第3个推荐）
        for b in scored:
            if b.get('cb_bonus', 0) >= 8 and b['code'] not in [p['code'] for p in pick_list]:
                cb_pick = {
                    'code': b['code'], 'market': b['market'], 'name': b['name'],
                    'price': b['price'], 'change_pct': b['change_pct'],
                    'signal': b['signal'], 'score': b['score'],
                    'details': {},
                    'top_reasons': [f'横盘突破(加分{b.get("cb_bonus",0)})'],
                    'risk_warning': '',
                }
                for key, val in b['details'].items():
                    s = val.get('score', 50)
                    cb_pick['details'][key] = {'score': s, 'signal': '买入' if s>=75 else '增持' if s>=60 else '持有' if s>=45 else '卖出'}
                pick_list.append(cb_pick)
                break

        # 早期启动第4股：低位刚放量，刚启动但未透支
        pick_codes = set(p['code'] for p in pick_list)
        early_candidates = []
        for b in scored:
            if b['code'] in pick_codes: continue
            if b.get('change_pct', 0) > 8: continue
            if b.get('range_pos', 100) > 30: continue
            if b.get('vol_ratio', 0) < 1.2: continue
            if b.get('cum_3d_chg', 0) < 2 or b.get('cum_3d_chg', 0) > 15: continue
            if b.get('score', 0) < 55: continue
            early_candidates.append(b)
        if early_candidates:
            # 按价格低位优先、量比次优排序
            early_candidates.sort(key=lambda r: (r.get('range_pos', 100), -r.get('vol_ratio', 0)))
            best = early_candidates[0]
            early_pick = {
                'code': best['code'], 'market': best['market'], 'name': best['name'],
                'price': best['price'], 'change_pct': best['change_pct'],
                'signal': best['signal'], 'score': best['score'],
                'details': {},
                'top_reasons': [f'低位{best.get("range_pos",0):.0f}%启动,量比{best.get("vol_ratio",0):.1f},3日涨{best.get("cum_3d_chg",0):.1f}%'],
                'risk_warning': '涨幅较大' if best['change_pct'] > 7 else '',
            }
            for key, val in best['details'].items():
                s = val.get('score', 50)
                early_pick['details'][key] = {'score': s, 'signal': '买入' if s>=75 else '增持' if s>=60 else '持有' if s>=45 else '卖出'}
            pick_list.append(early_pick)

        # 低位放量异动第5-6股：热点板块 + 低位 + 突然放量阳线
        pick_codes = set(p['code'] for p in pick_list)
        volume_candidates = []
        for b in scored:
            if b['code'] in pick_codes: continue
            if b.get('range_pos', 100) > 35: continue
            if not b.get('is_green'): continue
            if b.get('vol_day_ratio', 0) < 2.5: continue
            if b.get('change_pct', 0) > 9: continue
            volume_candidates.append(b)
        if volume_candidates:
            volume_candidates.sort(key=lambda r: -r.get('vol_day_ratio', 0))
            for best in volume_candidates[:2]:
                vol_pick = {
                    'code': best['code'], 'market': best['market'], 'name': best['name'],
                    'price': best['price'], 'change_pct': best['change_pct'],
                    'signal': best['signal'], 'score': best['score'],
                    'details': {},
                    'top_reasons': [f'低位{best.get("range_pos",0):.0f}%放量{best.get("vol_day_ratio",0):.1f}倍阳线'],
                    'risk_warning': '涨幅较大' if best['change_pct'] > 7 else '',
                }
                for key, val in best['details'].items():
                    s = val.get('score', 50)
                    vol_pick['details'][key] = {'score': s, 'signal': '买入' if s>=75 else '增持' if s>=60 else '持有' if s>=45 else '卖出'}
                pick_list.append(vol_pick)
                pick_codes.add(best['code'])

        payload = {
            'period': period, 'valid_from': valid_from, 'valid_until': valid_until,
            'status': 'ready', 'picks': pick_list,
            'computed_at': time.strftime('%Y-%m-%d %H:%M:%S'),
            'scanned_count': len(kline_map),
            'scan_summary': {'consolidation_breakout': cb_total, 'early_rise': len(early_candidates) if 'early_candidates' in dir() else 0, 'volume_surge': len(volume_candidates) if 'volume_candidates' in dir() else 0},
        }
        with open(DAILYPICK_FILE, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False)
        names = ' + '.join([f'{p["name"]}({p["code"]}) sc={p["score"]}' for p in pick_list])
        print(f'[dailypick] {period} picks -> {names}')
        return payload
    except Exception as e:
        print(f'[dailypick] 计算失败: {e}')
        import traceback; traceback.print_exc()
        return None
    finally:
        _DAILY_PICK_LOCK.release()

_SCHEDULER_RUNNING = False

def _save_snapshot(name, data):
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)
    path = os.path.join(SNAPSHOT_DIR, name)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)

def _run_scheduled_scans():
    """定时扫描：选股模式 + 板块追踪 + 预测记录 + 收盘验证"""

    now = time.localtime()
    # 非交易日跳过（周末+节假日）
    if not is_trading_day(now):
        return

    is_record = is_record_time(now.tm_hour, now.tm_min)
    is_verify = (now.tm_hour, now.tm_min) == (15, 10)

    print(f'[scheduler] 执行定时扫描 (记录={is_record}, 验证={is_verify})...')

    # 收集所有扫描到的股票
    all_scanned = []

    try:
        # 1. 选股模式扫描
        wl = load_watchlist()
        if wl:
            import concurrent.futures
            def f(s):
                try: k = fetch_kline(s['market']+s['code'], 120); return (s['code'], s['market'], s.get('name',s['code']), k)
                except: return (s['code'], s['market'], s.get('name',s['code']), [])
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as exe:
                kline_results = list(exe.map(f, wl))
            klines_all = {}; code_info = {}
            for code, market, name, k in kline_results:
                if len(k) >= 60:
                    klines_all[f'{market}{code}'] = k
                    code_info[f'{market}{code}'] = {'code':code,'market':market,'name':name}
                    if is_record:
                        all_scanned.append({'code':code,'market':market,'name':name,'kline':k})
            raw = scan_patterns(klines_all)
            patterns_out = []
            for full_code, matches in raw.items():
                info = code_info.get(full_code, {})
                for m in matches:
                    patterns_out.append({
                        'code': info.get('code',full_code), 'market': info.get('market','sh'),
                        'name': info.get('name',full_code), 'pattern_key': m['key'],
                        'pattern_name': m['name'], 'label': m['info'].get('label',''),
                        'detail': {k:v for k,v in m['info'].items() if k!='label'},
                    })
            _save_snapshot('patterns.json', {'patterns':patterns_out, 'count':len(patterns_out), 'stocks_matched':len(raw), 'time':time.strftime('%H:%M')})
            print(f'[scheduler] 选股模式: {len(patterns_out)} 个形态')
    except Exception as e:
        print(f'[scheduler] 选股模式扫描失败: {e}')

    try:
        # 2. 板块追踪扫描
        from engine.sectors import search_sectors, scan_sector_stocks, PREDEFINED
        matched = search_sectors(PREDEFINED, 'both')
        codes = [s['sector_code'] for s in matched if s['found']]
        if codes:
            result = scan_sector_stocks(codes, fetch_kline, max_stocks=20)
            result['time'] = time.strftime('%H:%M')
            _save_snapshot('sectors.json', result)
            print(f'[scheduler] 板块追踪: {result["total_patterns"]} 个形态, {len(codes)} 板块')
            # 记录本日板块热度前10
            try:
                secs = result.get("sectors", [])
                secs.sort(key=lambda x: -x.get("heat", 0))
                top10 = [s["name"] for s in secs[:10]]
                heat_file = os.path.join(DATA_DIR, 'snapshots', 'sector_heat.json')
                history = json.load(open(heat_file)) if os.path.exists(heat_file) else []
                today = time.strftime('%Y-%m-%d')
                if not history or history[-1].get("date") != today:
                    history.append({"date": today, "top10": top10})
                else:
                    history[-1]["top10"] = top10  # 当日多次扫描则更新
                history = history[-30:]
                json.dump(history, open(heat_file, 'w'), ensure_ascii=False)
            except Exception as e:
                print(f'[scheduler] 热度记录失败: {e}')
            if is_record:
                for sec in result.get("sectors", []):
                    for stk in sec.get("stocks", []):
                        code = stk.get("code", "")
                        market = stk.get("market", "sh")
                        name = stk.get("name", code)
                        # 去重: 已从自选股添加的不重复添加
                        if not any(s['code']==code and s['market']==market for s in all_scanned):
                            full_code = market + code
                            try:
                                k = fetch_kline(full_code, 120)
                                if len(k) >= 20:
                                    all_scanned.append({'code':code,'market':market,'name':name,'kline':k})
                            except:
                                pass
    except Exception as e:
        print(f'[scheduler] 板块扫描失败: {e}')

    # 3. 记录预测（15分钟间隔时间点）
    if is_record and all_scanned:
        from engine.indicators import calc_support_resistance
        # 批量获取实时行情
        codes_str = ','.join(f'{s["market"]}{s["code"]}' for s in all_scanned)
        quotes = fetch_tencent_quote(codes_str) if codes_str else {}
        # 加载板块数据（用于 sector_ctx）
        try:
            snap_path = os.path.join(os.path.dirname(__file__), 'data', 'snapshots', 'sectors.json')
            _sectors_snap = json.load(open(snap_path)) if os.path.exists(snap_path) else {}
            _sectors_list = _sectors_snap.get("sectors", [])
        except:
            _sectors_list = []
        recorded = 0
        for s in all_scanned:
            try:
                code, market = s['code'], s['market']
                quote = quotes.get(code, {})
                price = quote.get('price', s['kline'][-1]['close'] if s['kline'] else 0)
                if price <= 0:
                    continue
                # 查找板块上下文
                sector_ctx = None
                for sec in _sectors_list:
                    for stk in sec.get("stocks", []):
                        if stk.get("code") == code and stk.get("market") == market:
                            sector_ctx = {
                                "up_count": sec.get("up_count", 0),
                                "down_count": sec.get("down_count", 0),
                                "pattern_count": sec.get("pattern_count", 0),
                                "sector_name": sec.get("name", ""),
                            }
                            break
                    if sector_ctx:
                        break
                closes = [k['close'] for k in s['kline']]
                sr = calc_support_resistance(s['kline']) if len(s['kline']) >= 20 else {}
                pats = scan_patterns({market+code: s['kline']}) if len(s['kline']) >= 20 else {}
                patterns = pats.get(market+code, [])
                decision = make_decision(closes, s['kline'], patterns, sr, sector_ctx, quote, code=code, market=market)
                record_prediction(code, market, s['name'],
                                 decision['signal'], decision['score'], price,
                                 methods=decision.get('method_signals', {}))
                recorded += 1
            except:
                pass
        print(f'[scheduler] 预测记录: {recorded} 只股票')

    # 4. 收盘验证 + 多日追踪更新 (15:10)
    if is_verify:
        try:
            vcount = verify_predictions(fetch_kline)
            tcount = update_prediction_tracks(fetch_kline)
            print(f'[scheduler] 预测验证: {vcount} 条, 追踪更新: {tcount} 条')
        except Exception as e:
            print(f'[scheduler] 验证失败: {e}')

    # 5. 每日一股计算（仅 09:25 和 15:01 触发，避免重算导致CPU打满）
    hm = (now.tm_hour, now.tm_min)
    if hm in ((9, 25), (15, 1)):
        # 检查是否已算过（避免多次触发）
        if os.path.exists(DAILYPICK_FILE):
            try:
                with open(DAILYPICK_FILE) as f:
                    cached = json.load(f)
                if cached.get('period') == ('morning' if hm == (9,25) else 'afternoon'):
                    print(f'[scheduler] 每日一股已存在，跳过')
                    hm = None  # 标记已处理
            except:
                pass
        if hm:  # 需要重新计算
            period = 'morning' if hm == (9,25) else 'afternoon'
            print(f'[scheduler] 触发 每日一股({period})...')
            threading.Thread(target=compute_daily_pick, args=(period,), daemon=True).start()

    # 6. 今日走势预测(09:25) + 收盘验证+次日预测(15:01)
    hm = (now.tm_hour, now.tm_min)
    if hm == (9, 25):
        wl = load_watchlist()
        if wl:
            codes_str = ','.join([s['market'] + s['code'] for s in wl])
            quotes = fetch_tencent_quote(codes_str) if codes_str else {}
            threading.Thread(target=predict_intraday, args=(wl, quotes), daemon=True).start()
    elif hm == (15, 1):
        threading.Thread(target=verify_intraday, daemon=True).start()
        wl = load_watchlist()
        if wl:
            try:
                ncount = record_nextday_prediction(wl, fetch_kline)
                print(f'[scheduler] 次日预测记录: {ncount} 只')
            except Exception as e:
                print(f'[scheduler] 次日预测记录失败: {e}')
        try:
            vcount = verify_nextday_predictions(fetch_kline)
            print(f'[scheduler] 次日预测验证: {vcount} 条')
        except Exception as e:
            print(f'[scheduler] 次日预测验证失败: {e}')
        # ML模型每周重训练
        try:
            from engine.ml_scorer import train as ml_train
            import os.path as _p
            model_file = _p.join(_p.dirname(__file__), 'data', 'ml', 'model.pkl')
            if not _p.exists(model_file) or (time.time() - _p.getmtime(model_file) > 86400):
                ml_train()
        except:
            pass

    print(f'[scheduler] 扫描完成')

def _scheduler_loop():
    """每30秒检查一次，到点执行"""
    global _SCHEDULER_RUNNING
    _SCHEDULER_RUNNING = True
    _run_history = set()  # (date, hour, min) 已执行的时段
    while _SCHEDULER_RUNNING:
        try:
            now = time.localtime()
            hm = (now.tm_hour, now.tm_min)
            key = (now.tm_year, now.tm_yday, now.tm_hour, now.tm_min)
            if hm in SCHEDULE_TIMES and key not in _run_history:
                _run_history.add(key)
                _run_scheduled_scans()
        except:
            pass
        time.sleep(30)

# 启动调度器
threading.Thread(target=_scheduler_loop, daemon=True).start()

@app.route('/api/snapshots')
def get_snapshots():
    """获取最新快照"""
    result = {'time': None}
    for name in ['patterns.json', 'sectors.json']:
        path = os.path.join(SNAPSHOT_DIR, name)
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    result[name.replace('.json','')] = json.load(f)
            except: pass
    if result.get('patterns'):
        result['time'] = result['patterns'].get('time') or result.get('time')
    return jsonify(result)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    ip = get_local_ip()
    print(f'=== AI 量化选股系统 ===')
    print(f'   本地: http://127.0.0.1:{port}')
    if ip != '127.0.0.1':
        print(f'   局域网: http://{ip}:{port}')
    print(f'   自选股文件: {WATCHLIST_FILE}')
    print(f'   Ctrl+C 停止')
    print(f'   部署模式: {"云服务器" if os.environ.get("PORT") else "本地开发"}')
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
