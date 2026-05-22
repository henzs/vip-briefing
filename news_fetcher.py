"""종목별 최근 뉴스 수집.

- 국내(KR): 네이버 통합검색 뉴스 결과 → Jina Reader로 헤드라인 추출
- 해외(US): yfinance의 .news 속성
실패해도 빈 리스트 반환 (분석 진행 중단되지 않도록).
"""
import re
from datetime import datetime

import requests
import yfinance as yf


def _fetch_naver_search_news(query: str, limit: int = 5) -> list[dict]:
    """네이버 통합검색의 뉴스 탭에서 종목 관련 헤드라인 수집 (Jina Reader 사용)."""
    if not query:
        return []

    url = (
        "https://r.jina.ai/https://search.naver.com/search.naver"
        f"?where=news&query={query}"
    )
    try:
        resp = requests.get(
            url,
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0", "Accept": "text/plain"},
        )
        if resp.status_code != 200:
            return []
        text = resp.text
    except Exception:
        return []

    news: list[dict] = []
    seen: set[str] = set()

    # 마크다운 링크 패턴 [제목](url) — 비이미지·비네비게이션만
    link_pattern = re.compile(r"\[([^\[\]]+)\]\((https?://[^)]+)\)")

    for m in link_pattern.finditer(text):
        title = m.group(1).strip()
        url_str = m.group(2)

        # 네비게이션·이미지·검색결과외 링크 필터
        if any(x in url_str for x in (
            "pstatic.net",
            "naver.com/press",
            "naver.com/main",
            "search.pstatic",
            "shopping.naver",
            "blog.naver",
            "cafe.naver",
        )):
            continue

        # 마크업·HTML 엔티티 정리
        title = re.sub(r"</?mark>", "", title).strip()
        title = (
            title.replace("&quot;", '"')
            .replace("&amp;", "&")
            .replace("&#39;", "'")
            .replace("&lt;", "<")
            .replace("&gt;", ">")
        )

        # 너무 짧거나 한글 없는 항목 제외
        if not re.search(r"[가-힣]", title):
            continue
        if len(title) < 10:
            continue

        # 200자 초과는 잘라서 토큰 절약
        if len(title) > 200:
            title = title[:200].rstrip() + "..."

        if title in seen:
            continue
        seen.add(title)
        news.append({"title": title})

        if len(news) >= limit:
            break

    return news[:limit]


def _fetch_yfinance_news(ticker: str, limit: int = 5) -> list[dict]:
    """yfinance에서 해외 종목 뉴스 수집."""
    if not ticker:
        return []
    try:
        items = (yf.Ticker(ticker).news or [])[:limit]
    except Exception:
        return []

    news: list[dict] = []
    for item in items:
        title = (
            item.get("title")
            or item.get("content", {}).get("title", "")
            or ""
        )
        pub = (
            item.get("providerPublishTime")
            or item.get("pubDate")
            or item.get("content", {}).get("pubDate", "")
        )
        date_str = ""
        if isinstance(pub, (int, float)):
            try:
                date_str = datetime.fromtimestamp(pub).strftime("%Y-%m-%d")
            except Exception:
                date_str = ""
        elif isinstance(pub, str):
            date_str = pub[:10]
        if title:
            news.append({"date": date_str, "title": title.strip()})

    return news[:limit]


def fetch_news_for_stock(
    ticker: str,
    market: str = "KR",
    limit: int = 5,
    name: str | None = None,
) -> list[dict]:
    """종목 시장 구분에 따라 적절한 뉴스 소스에서 수집.

    KR의 경우 name(종목명)이 있으면 네이버 검색의 정확도가 높아진다.
    """
    if market == "US":
        return _fetch_yfinance_news(ticker, limit)
    # KR: 종목명 우선, 없으면 티커
    query = (name or ticker or "").strip()
    if not query:
        return []
    return _fetch_naver_search_news(query, limit)
