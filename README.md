# AI 뉴스리포트 대시보드

- 매시간 자동 크롤링 (GitHub Actions)
- 시장지표/환율 자동 갱신
- 테마 Top5 & 월간 키워드 맵 (NewsAPI 페이지네이션 적용)
- 최신 헤드라인 10건 (상위 테마 기준)
- 텔레그램 알림(옵션)

### 환경변수(Secrets)
- `NEWSAPI_KEY` (필수)  
- `TELEGRAM_TOKEN` / `TELEGRAM_CHAT_ID` (옵션)

### 수동 실행
GitHub → **Actions** → `Update AI News Dashboard (hourly)` → **Run workflow**
