import os
import json
import datetime
import pandas as pd
from newsapi import NewsApiClient

# ✅ 환경 변수 (GitHub Secrets로 등록)
NEWSAPI_KEY = os.getenv("810d72c58b114db5b10a7a4b4a196dce")
TELEGRAM_BOT_TOKEN = os.getenv("AAEfuIvqm2jTBBxQpNZA351T2FHMYuG3Wrs")
TELEGRAM_CHAT_ID = os.getenv("8202492756")

# ✅ API 초기화
newsapi = NewsApiClient(api_key=NEWSAPI_KEY)
today = datetime.date.today()
from_date = (today - datetime.timedelta(days=2)).isoformat()

# ✅ 주요 테마 / 종목 리스트
themes = {
    "AI 반도체": ["삼성전자", "SK하이닉스", "엘비세미콘", "티씨케이"],
    "2차전지": ["엘앤에프", "에코프로비엠", "포스코퓨처엠", "천보"],
    "로봇": ["레인보우로보틱스", "유진로봇", "로보스타", "휴림로봇"],
    "바이오": ["셀트리온", "삼성바이오로직스", "HLB", "유한양행"]
}

# ✅ 뉴스 수집
def fetch_news(query):
    try:
        articles = newsapi.get_everything(
            q=query,
            language="ko",
            from_param=from_date,
            sort_by="publishedAt",
            page_size=10
        )
        return [
            {"title": a["title"], "url": a["url"], "source": a["source"]["name"]}
            for a in articles.get("articles", [])
        ]
    except Exception as e:
        print(f"❌ Error fetching news for {query}: {e}")
        return []

# ✅ 전체 뉴스 수집 (Top 10)
headline_query = "AI OR 반도체 OR 주식 OR 산업 OR 경제 OR 삼성전자 OR SK하이닉스"
headlines = fetch_news(headline_query)
os.makedirs("data", exist_ok=True)
with open("data/news_top10.json", "w", encoding="utf-8") as f:
    json.dump(headlines, f, ensure_ascii=False, indent=2)

# ✅ 테마별 키워드맵 + 종목별 최신뉴스 2건
theme_summary = []
theme_news_archive = {}

for theme, stocks in themes.items():
    theme_keywords = ", ".join(stocks)
    total_news = []
    for stock in stocks:
        news_list = fetch_news(stock)
        total_news.extend(news_list[:2])  # 종목당 2건만
        theme_news_archive[stock] = news_list[:2]
    theme_summary.append({
        "theme": theme,
        "count": len(total_news),
        "keywords": theme_keywords
    })

# ✅ 저장 (테마 Top5)
theme_summary_sorted = sorted(theme_summary, key=lambda x: x["count"], reverse=True)
with open("data/theme_top5.json", "w", encoding="utf-8") as f:
    json.dump(theme_summary_sorted[:5], f, ensure_ascii=False, indent=2)

# ✅ 저장 (종목별 뉴스 아카이브)
with open("data/theme_stock_news.json", "w", encoding="utf-8") as f:
    json.dump(theme_news_archive, f, ensure_ascii=False, indent=2)

# ✅ 월간 키워드맵 (간단 빈도 카운트)
keyword_df = pd.DataFrame([
    {"keyword": kw, "count": t["count"]}
    for t in theme_summary_sorted[:5]
    for kw in t["keywords"].split(", ")
])
keyword_df.to_csv("data/monthly_keywordmap.csv", index=False, encoding="utf-8-sig")

# ✅ 텔레그램 알림 전송
if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
    import requests
    msg = f"✅ AI 뉴스리포트 자동 업데이트 완료 ({datetime.datetime.now().strftime('%Y-%m-%d %H:%M')})\n"
    msg += f"Top 뉴스: {headlines[0]['title'] if headlines else '없음'}"
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg})
    print("📨 Telegram notification sent.")
else:
    print("⚠️ TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set")

print("✅ Dashboard data updated successfully.")
