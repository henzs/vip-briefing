"""포트폴리오 정규화: 중복 합산, KR/US 판별, 종목명→티커 매핑.

매핑 전략:
  1. 정적 맵 (STATIC_NAME_TO_TICKER) — 주요 종목 즉시 매핑
  2. 정적 맵 부분 일치 — 후보 중 길이 차이 최소
  3. (실패 시) Claude Haiku로 KRX 6자리 코드 추론 (resolve_kr_via_haiku)
  4. 영문 종목명 → 해외 분류 (Yahoo 티커는 fetcher_overseas에서 처리)
"""
import re

from pykrx import stock as krx

# ─── 주요 종목 하드코딩 (index.html TICKER_MAP과 동일) ────────────────────
STATIC_NAME_TO_TICKER: dict[str, str] = {
    "삼성전자": "005930", "SK하이닉스": "000660", "LG에너지솔루션": "373220",
    "삼성바이오로직스": "207940", "현대차": "005380", "기아": "000270",
    "POSCO홀딩스": "005490", "셀트리온": "068270", "KB금융": "105560",
    "신한지주": "055550", "카카오": "035720", "NAVER": "035420",
    "삼성SDI": "006400", "LG화학": "051910", "현대모비스": "012330",
    "하나금융지주": "086790", "우리금융지주": "316140", "삼성물산": "028260",
    "SK이노베이션": "096770", "LG전자": "066570", "롯데케미칼": "011170",
    "고려아연": "010130", "두산에너빌리티": "034020", "한국전력": "015760",
    "KT&G": "033780", "SK텔레콤": "017670", "KT": "030200",
    "삼성생명": "032830", "한화에어로스페이스": "012450", "포스코퓨처엠": "003670",
    "에코프로비엠": "247540", "에코프로": "086520", "카카오뱅크": "323410",
    "크래프톤": "259960", "카카오페이": "377300", "하이브": "352820",
    "동아엘텍": "088130", "삼성전기": "009150", "엔씨소프트": "036570",
    "두산밥캣": "241560", "한미반도체": "042700", "리노공업": "058470",
    "솔브레인": "357780", "에스에프에이": "056190", "코스모신소재": "005070",
    "SK바이오사이언스": "302440", "HLB": "028300", "알테오젠": "196170",
    "셀트리온헬스케어": "091990", "씨젠": "096530", "유한양행": "000100",
    "삼성중공업": "010140", "HD현대중공업": "329180", "HD한국조선해양": "009540",
    "현대건설": "000720", "GS건설": "006360", "대우건설": "047040",
}


def _normalize(name: str) -> str:
    """(일반), (담보), (신용) 등 괄호 제거."""
    return re.sub(r"\s*\([^)]*\)", "", name).strip()


def deduplicate(portfolio: list[dict]) -> list[dict]:
    """같은 종목명(정규화 후)이면 비중·잔고수량·평가금액·평가손익금액 합산."""
    merged: dict[str, dict] = {}
    for h in portfolio:
        key = _normalize(h["종목명"])
        if key in merged:
            merged[key]["비중"] = round(merged[key].get("비중", 0) + h.get("비중", 0), 4)
            for field in ("잔고수량", "평가금액", "평가손익금액"):
                if h.get(field) is not None:
                    merged[key][field] = (merged[key].get(field) or 0) + (h.get(field) or 0)
        else:
            entry = dict(h)
            entry["종목명"] = key
            merged[key] = entry
    return list(merged.values())


def is_overseas_name(name: str) -> bool:
    has_korean = bool(re.search(r"[가-힣]", name))
    has_english = bool(re.search(r"[A-Za-z]", name))
    return not has_korean and has_english


def is_kr_ticker(ticker: str | None) -> bool:
    return bool(ticker) and bool(re.fullmatch(r"\d{6}", ticker))


def is_us_ticker(ticker: str) -> bool:
    return bool(re.fullmatch(r"[A-Z]{1,7}", ticker))


def name_to_ticker_static(name: str) -> str | None:
    """정적 맵 정확 일치만 — 부분 일치는 셀트리온/셀트리온제약 같은 충돌 일으킴."""
    return STATIC_NAME_TO_TICKER.get(name)


def verify_kr_ticker(ticker: str) -> str | None:
    """KRX에 실재하는 6자리 코드인지 확인. 유효하면 종목명 반환, 아니면 None."""
    if not is_kr_ticker(ticker):
        return None
    try:
        name = krx.get_market_ticker_name(ticker)
        return name if name else None
    except Exception:
        return None


_NAVER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "ko-KR,ko;q=0.9",
}


def resolve_kr_via_naver_search(name: str) -> str | None:
    """네이버 통합검색에서 한국 종목명 → 6자리 KRX 코드 추출.
    Haiku 환각 없이 100% 실제 코드 반환. KRX로 검증.
    """
    import requests

    try:
        resp = requests.get(
            "https://search.naver.com/search.naver",
            params={"query": f"{name} 주가"},
            headers=_NAVER_HEADERS,
            timeout=10,
        )
        resp.encoding = "utf-8"
        # finance.naver.com 링크 안의 code=XXXXXX 패턴 (가장 신뢰도 높음)
        codes = re.findall(r"finance\.naver\.com[^\"']*code=(\d{6})", resp.text)
        if not codes:
            return None
        # 가장 많이 등장한 코드 (검색 결과 상단 종목)
        from collections import Counter
        ticker, _ = Counter(codes).most_common(1)[0]
        # KRX 실재 검증
        if verify_kr_ticker(ticker):
            return ticker
        return None
    except Exception:
        return None


def classify_and_map(portfolio: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    """각 종목에 market/ticker 부여 (정적 맵만 사용, Haiku 호출 없음).

    Returns: (portfolio, kr_pending, overseas_pending)
      - kr_pending: 한국 종목인데 정적 맵에 없음 → Haiku로 식별 필요
      - overseas_pending: 영문 종목 → Yahoo 티커 식별 필요
    """
    kr_pending: list[dict] = []
    overseas_pending: list[dict] = []

    for h in portfolio:
        name = h["종목명"]
        if is_overseas_name(name):
            h["ticker"] = None
            h["market"] = "US_pending"
            overseas_pending.append(h)
            continue

        ticker = name_to_ticker_static(name)
        if ticker and is_kr_ticker(ticker):
            h["ticker"] = ticker
            h["market"] = "KR"
        else:
            h["ticker"] = None
            h["market"] = "KR_pending"
            kr_pending.append(h)

    return portfolio, kr_pending, overseas_pending
