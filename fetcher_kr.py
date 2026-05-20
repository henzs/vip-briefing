"""국내 주식 데이터 수집: KRX(pykrx) + 네이버 금융 + 에프엔가이드."""
from datetime import datetime, timedelta

import requests
from bs4 import BeautifulSoup
from pykrx import stock as krx

NOT_AVAILABLE = "조회 불가"
REQUEST_TIMEOUT = 15

NAVER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer": "https://finance.naver.com/",
}
FNGUIDE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer": "https://comp.fnguide.com/",
}


def _recent_trade_date() -> str:
    for i in range(10):
        d = (datetime.now() - timedelta(days=i)).strftime("%Y%m%d")
        try:
            if not krx.get_market_ohlcv_by_date(d, d, "005930").empty:
                return d
        except Exception:
            continue
    return datetime.now().strftime("%Y%m%d")


def _clean(text: str) -> str:
    return text.strip().replace(",", "").replace(" ", "").replace("\xa0", "")


# ─── KRX 데이터 ──────────────────────────────────────────────────────────────
def get_krx_data(ticker: str, trade_date: str) -> dict:
    """현재가·시가총액·52주 고저·외국인 보유비율."""
    result = {
        "source": "KRX", "trade_date": trade_date,
        "current_price": NOT_AVAILABLE, "volume": NOT_AVAILABLE,
        "market_cap": NOT_AVAILABLE,
        "week52_high": NOT_AVAILABLE, "week52_low": NOT_AVAILABLE,
        "foreign_ownership_ratio": NOT_AVAILABLE,
    }
    try:
        ohlcv = krx.get_market_ohlcv_by_date(trade_date, trade_date, ticker)
        if not ohlcv.empty:
            row = ohlcv.iloc[-1]
            if "종가" in row.index:
                result["current_price"] = int(row["종가"])
            if "거래량" in row.index:
                result["volume"] = int(row["거래량"])
    except Exception:
        pass

    try:
        cap_df = krx.get_market_cap_by_date(trade_date, trade_date, ticker)
        if not cap_df.empty:
            col = "시가총액" if "시가총액" in cap_df.columns else cap_df.columns[0]
            result["market_cap"] = int(cap_df.iloc[-1][col])
    except Exception:
        pass

    try:
        one_year_ago = (datetime.strptime(trade_date, "%Y%m%d") - timedelta(days=365)).strftime("%Y%m%d")
        yearly = krx.get_market_ohlcv_by_date(one_year_ago, trade_date, ticker)
        if not yearly.empty:
            hi = "고가" if "고가" in yearly.columns else yearly.columns[1]
            lo = "저가" if "저가" in yearly.columns else yearly.columns[2]
            result["week52_high"] = int(yearly[hi].max())
            result["week52_low"] = int(yearly[lo].min())
    except Exception:
        pass

    try:
        foreign_df = krx.get_exhaustion_rates_of_foreign_investment_by_date(trade_date, trade_date, ticker)
        if not foreign_df.empty:
            for col in ["보유비율", "지분율"]:
                if col in foreign_df.columns:
                    result["foreign_ownership_ratio"] = round(float(foreign_df.iloc[-1][col]), 2)
                    break
    except Exception:
        pass

    return result


# ─── 네이버 금융 데이터 ──────────────────────────────────────────────────────
def get_naver_finance_data(ticker: str) -> dict:
    """PER/EPS/PBR/BPS/배당수익률/목표주가."""
    result = {
        "source": "네이버 금융",
        "per": NOT_AVAILABLE, "pbr": NOT_AVAILABLE,
        "eps": NOT_AVAILABLE, "bps": NOT_AVAILABLE,
        "dividend_yield": NOT_AVAILABLE, "analyst_target_price": NOT_AVAILABLE,
    }
    try:
        url = f"https://finance.naver.com/item/coinfo.naver?code={ticker}"
        resp = requests.get(url, headers=NAVER_HEADERS, timeout=REQUEST_TIMEOUT)
        resp.encoding = "euc-kr"
        soup = BeautifulSoup(resp.text, "html.parser")

        for field, em_id in [("per", "_per"), ("eps", "_eps")]:
            em = soup.find("em", id=em_id)
            if em:
                val = _clean(em.text)
                if val and val.lower() not in ("n/a", "-", "0", ""):
                    result[field] = val

        dvr_em = soup.find("em", id="_dvr")
        if dvr_em:
            val = _clean(dvr_em.text)
            if val and val.lower() not in ("n/a", "-", "0", ""):
                result["dividend_yield"] = val + "%"

        for th in soup.find_all("th"):
            if "PBR" in th.text and "BPS" in th.text:
                row = th.find_parent("tr")
                if row:
                    td = row.find("td")
                    if td:
                        ems = td.find_all("em")
                        if len(ems) >= 1:
                            v = _clean(ems[0].text)
                            if v and v.lower() not in ("n/a", "-", "0", ""):
                                result["pbr"] = v
                        if len(ems) >= 2:
                            v = _clean(ems[1].text)
                            if v and v.lower() not in ("n/a", "-", "0", ""):
                                result["bps"] = v
                break

        for caption in soup.find_all("caption"):
            if "투자의견" in caption.text:
                table = caption.find_parent("table")
                if table:
                    for th in table.find_all("th"):
                        if "목표주가" in th.text:
                            row = th.find_parent("tr")
                            if row:
                                td = row.find("td")
                                if td:
                                    ems = td.find_all("em")
                                    if len(ems) >= 2:
                                        try:
                                            result["analyst_target_price"] = int(_clean(ems[1].text))
                                        except ValueError:
                                            pass
                            break
                break
    except Exception:
        pass

    return result


# ─── 에프엔가이드 (PBR·외국인비율 보조) ──────────────────────────────────────
def get_fnguide_data(ticker: str) -> dict:
    result = {"source": "에프엔가이드", "pbr": NOT_AVAILABLE, "foreign_ownership_ratio": NOT_AVAILABLE}
    try:
        url = (f"https://comp.fnguide.com/SVO2/ASP/SVD_Main.asp"
               f"?pGB=1&gicode=A{ticker}&cID=&MenuYn=Y&ReportGB=&NewMenuID=11&stkGb=701")
        resp = requests.get(url, headers=FNGUIDE_HEADERS, timeout=REQUEST_TIMEOUT)
        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")

        foreign_span = soup.find(id="svdMainChartTxt12")
        if foreign_span:
            val = foreign_span.get_text(strip=True).replace(",", "")
            try:
                result["foreign_ownership_ratio"] = round(float(val), 2)
            except ValueError:
                pass

        for table in soup.find_all("table"):
            cap = table.find("caption")
            if not cap or "Financial Highlight" not in cap.get_text():
                continue
            for tr in table.find_all("tr"):
                th = tr.find("th")
                if not th or "PBR" not in th.get_text():
                    continue
                tds = tr.find_all("td")
                for td in reversed(tds):
                    val = td.get_text(strip=True).replace(",", "")
                    if val and val.lower() not in ("n/a", "-", ""):
                        result["pbr"] = val
                        break
                if result["pbr"] != NOT_AVAILABLE:
                    break
            if result["pbr"] != NOT_AVAILABLE:
                break
    except Exception:
        pass

    return result


# ─── 통합 ────────────────────────────────────────────────────────────────────
def get_stock_data(ticker: str) -> dict:
    trade_date = _recent_trade_date()
    name = NOT_AVAILABLE
    try:
        name = krx.get_market_ticker_name(ticker)
    except Exception:
        pass

    krx_data = get_krx_data(ticker, trade_date)
    naver_data = get_naver_finance_data(ticker)
    fnguide_data = get_fnguide_data(ticker)

    # 에프엔가이드 우선
    if fnguide_data.get("pbr") not in (NOT_AVAILABLE, None):
        naver_data["pbr"] = fnguide_data["pbr"]
    if fnguide_data.get("foreign_ownership_ratio") not in (NOT_AVAILABLE, None):
        krx_data["foreign_ownership_ratio"] = fnguide_data["foreign_ownership_ratio"]

    return {"ticker": ticker, "name": name, "krx": krx_data, "naver_finance": naver_data}
