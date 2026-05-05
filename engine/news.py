"""新闻采集与简单情感分析"""
import requests
import re
import json

NEWS_CACHE = {}

def fetch_news(code, market='sh'):
    """获取股票相关新闻(东方财富)"""
    secid = '0.' + code if market == 'sz' else '1.' + code
    url = f'https://push2.eastmoney.com/api/qt/stock/news/get?secid={secid}&count=20'
    try:
        r = requests.get(url, timeout=5, headers={'User-Agent': 'Mozilla/5.0'})
        data = r.json()
        items = data.get('data', []) if isinstance(data, dict) else []
        results = []
        for item in items[:15]:
            title = item.get('title', item.get('art', '')) if isinstance(item, dict) else str(item)
            results.append({
                'title': title,
                'source': item.get('source', '财经媒体') if isinstance(item, dict) else '东方财富',
                'time': item.get('date', '') if isinstance(item, dict) else '',
            })
        return results
    except:
        return _mock_news(code, market)


def _mock_news(code, market):
    """当API不可用时返回模拟新闻"""
    import random
    headlines = [
        f"公司{code}签署重大战略合作协议，布局新业务领域",
        "行业政策利好，板块整体走强",
        f"{code}发布业绩预告，净利润同比增长",
        "券商研报：看好该股长期投资价值",
        "公司公告：获得重要专利授权",
        "市场分析：行业景气度持续提升",
        f"{code}获机构集中调研，关注业务进展",
        "产业资本增持，彰显发展信心",
        "行业迎来政策窗口期，龙头受益明显",
        f"{code}新技术突破，市场前景广阔",
    ]
    return [{'title': random.choice(headlines), 'source': '模拟数据', 'time': '今日'} for _ in range(5)]


def analyze_sentiment(news_list):
    """简单情感分析 - 基于关键词"""
    pos_words = ['利好', '增长', '突破', '增持', '受益', '看好', '提升', '战略合作',
                 '盈利', '龙头', '领先', '新高', '获批', '提振', '超预期']
    neg_words = ['减持', '亏损', '下跌', '风险', '利空', '处罚', '诉讼', '违约',
                 '下调', '预警', 'st', '退市', '立案', '调查', '跌停']

    total_score = 0
    if not news_list:
        return 0, []

    analyzed = []
    for news in news_list:
        title = news.get('title', '')
        score = 0
        for w in pos_words:
            if w in title: score += 1
        for w in neg_words:
            if w in title: score -= 1
        sentiment = 'positive' if score > 0 else ('negative' if score < 0 else 'neutral')
        analyzed.append({**news, 'sentiment': sentiment, 'score': score})
        total_score += score

    avg = total_score / len(news_list) if news_list else 0
    # 归一化到 -1 ~ 1
    normalized = max(-1, min(1, avg / 3))
    return normalized, analyzed
