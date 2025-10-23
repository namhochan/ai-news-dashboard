# -*- coding: utf-8 -*-
"""
GitHub Actions에서 호출되는 데이터 파이프라인 최소 버전.
필요한 출력 파일들을 data/ 아래에 생성해 둡니다.
실패하지 않도록 예외를 모두 잡고, 기본 구조만 채워 둡니다.
"""

import json
import os
from datetime import datetime, timezone, timedelta

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

def write_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

def main():
    # KST 타임스탬프
    kst = timezone(timedelta(hours=9))
    now_str = datetime.now(kst).strftime("%Y-%m-%d %H:%M:%S (KST)")

    # 최소 더미 데이터 (대시보드가 읽을 파일들)
    market = {
        "updated_at": now_str,
        "kospi": {"value": None, "change_pct": None},
        "kosdaq": {"value": None, "change_pct": None},
        "usdkrw": {"value": None, "change_pct": None},
        "memo": "지표/환율은 추후 소스 연동 예정"
    }
    write_json(os.path.join(DATA_DIR, "market_today.json"), market)

    # 뉴스 Top10 (비어있을 수 있음)
    headlines = {
        "updated_at": now_str,
        "items": []  # [{"title": "...","link":"..."}] 형태로 채워질 예정
    }
    write_json(os.path.join(DATA_DIR, "headlines_top10.json"), headlines)

    # 뉴스 100건 원본 리스트
    news100 = {
        "updated_at": now_str,
        "items": []  # [{"title": "...","link":"...","source":"...","published":"..."}]
    }
    write_json(os.path.join(DATA_DIR, "news_100.json"), news100)

    # 메인 테마 Top5
    theme_top5 = {
        "updated_at": now_str,
        "themes": []  # [{"theme":"AI","count": 23, "score": 87, "rep_stocks":["..."], "sample_link":"..."}]
    }
    write_json(os.path.join(DATA_DIR, "theme_top5.json"), theme_top5)

    # 보조 테마 5
    theme_secondary5 = {
        "updated_at": now_str,
        "themes": []
    }
    write_json(os.path.join(DATA_DIR, "theme_secondary5.json"), theme_secondary5)

    # 월간 키워드맵
    keyword_map = {
        "updated_at": now_str,
        "keywords": []  # [{"keyword":"AI","count": 42}, ...]
    }
    write_json(os.path.join(DATA_DIR, "keyword_map_month.json"), keyword_map)

    print("[OK] Dummy data files written to /data")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        # 절대 실패하지 않도록 보호
        print(f"[WARN] pipeline error suppressed: {e}")
        # 그래도 최소 파일은 만들어 둠
        os.makedirs(DATA_DIR, exist_ok=True)
        for name in [
            "market_today.json",
            "headlines_top10.json",
            "news_100.json",
            "theme_top5.json",
            "theme_secondary5.json",
            "keyword_map_month.json",
        ]:
            path = os.path.join(DATA_DIR, name)
            if not os.path.exists(path):
                with open(path, "w", encoding="utf-8") as f:
                    json.dump({"items": []}, f, ensure_ascii=False)
        raise SystemExit(0)
