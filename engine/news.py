"""新闻采集与简单情感分析"""
import time
import json
import re

NEWS_CACHE = {}
CACHE_TTL = 300  # 5分钟缓存

def _clean_title(text):
    """去除 East Money 搜索结果中的 <em> 高亮标签和空白"""
    text = re.sub(r'<[^>]+>', '', text)
    return text.strip()

NEWS_CACHE = {}
CACHE_TTL = 300  # 5分钟缓存

def fetch_news(code, market='sh'):
    """获取股票相关新闻(东方财富 search API)，带5分钟缓存"""
    cache_key = f'{code}_{market}'
    now = time.time()
    cached = NEWS_CACHE.get(cache_key)
    if cached and now - cached['ts'] < CACHE_TTL:
        return cached['data']

    try:
        import akshare as ak
        df = ak.stock_news_em(symbol=code)
        results = []
        for _, row in df.head(15).iterrows():
            results.append({
                'title': _clean_title(row.get('新闻标题', '')),
                'source': row.get('文章来源', '财经媒体'),
                'time': str(row.get('发布时间', '')),
            })
        NEWS_CACHE[cache_key] = {'ts': now, 'data': results}
        return results
    except Exception:
        return []  # 无数据时不返回模拟数据，前端显示为空


def analyze_sentiment(news_list):
    """简单情感分析 - 基于关键词"""
    pos_words = ['利好', '增长', '突破', '增持', '受益', '看好', '提升', '战略合作',
                 '盈利', '龙头', '领先', '新高', '获批', '提振', '超预期',
                 '净利', '走强', '流入', '上涨', '涨幅', '升']
    neg_words = ['减持', '亏损', '下跌', '风险', '利空', '处罚', '诉讼', '违约',
                 '下调', '预警', 'st', '退市', '立案', '调查', '跌停',
                 '流出', '跌幅', '回落', '承压', '疲软', '下滑']

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
