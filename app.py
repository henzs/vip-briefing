"""VIP 포트폴리오 브리핑 — Streamlit 웹앱.

구조:
  사이드바: API 키 / 고객명 / RM 이름
  본문: 이미지 업로드 → 분석 실행 → 종목·시세·AI 분석 표시 → DOCX 다운로드
"""
import os
import sys
import traceback
from datetime import datetime

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

# .env 파일에서 환경변수 로드 (로컬용 — Streamlit Cloud에서는 무시됨)
load_dotenv()


def _get_secret(key: str, default: str = "") -> str:
    """Streamlit Cloud Secrets 우선, 없으면 로컬 .env, 둘 다 없으면 default.
    배포(Cloud)와 로컬 실행을 같은 코드로 지원하기 위함.
    """
    try:
        if key in st.secrets:
            return st.secrets[key]
    except Exception:
        # 로컬에서 .streamlit/secrets.toml이 없으면 예외 — 환경변수로 fallback
        pass
    return os.getenv(key, default)


from ai_analysis import analyze_top_holdings
from fetcher_kr import get_stock_data as get_kr_data
from fetcher_overseas import get_yahoo_data, identify_ticker
from image_parser import detect_media_type, parse_portfolio_image
from macro_briefing import fetch_indices, generate_macro_briefing
from portfolio import (
    classify_and_map,
    deduplicate,
    is_overseas_name,
    is_us_ticker,
    name_to_ticker_static,
    resolve_kr_via_naver_search,
)
from portfolio_health import diagnose_health
from rebalancing import generate_rebalancing
from report_builder import build_detail, build_summary
from email_template import build_email
from flow_data import fetch_30day_flow
from stock_chart import generate_price_chart
from valuation_compare import get_per_comparison

# 센터 내부 접근 비밀번호
# 변경 방법:
#   - 로컬: .env 파일에 ACCESS_PASSWORD=새비밀번호 추가
#   - Streamlit Cloud: 앱 설정 → Secrets 에 ACCESS_PASSWORD = "새비밀번호" 추가
# 둘 다 없으면 아래 기본값(0207) 사용
ACCESS_PASSWORD = _get_secret("ACCESS_PASSWORD", "0207")

# ─── 섹터 매핑 (index.html에서 가져옴) ─────────────────────────────────────
SECTOR_MAP: dict[str, str] = {
    "005930": "반도체", "000660": "반도체", "042700": "반도체장비",
    "009150": "전자부품", "058470": "IT부품",
    "373220": "2차전지", "006400": "2차전지", "003670": "2차전지소재",
    "247540": "2차전지소재", "086520": "2차전지소재",
    "207940": "바이오", "068270": "바이오", "028300": "바이오",
    "196170": "바이오", "302440": "바이오", "096530": "바이오",
    "000100": "바이오", "091990": "바이오", "357780": "소재",
    "005380": "자동차", "000270": "자동차", "012330": "자동차부품",
    "241560": "기계", "005490": "철강", "010130": "비철금속",
    "105560": "금융", "055550": "금융", "086790": "금융", "316140": "금융",
    "032830": "보험", "377300": "핀테크", "323410": "핀테크",
    "035720": "IT플랫폼", "035420": "IT플랫폼",
    "036570": "게임", "259960": "게임",
    "051910": "화학", "011170": "화학", "096770": "에너지/화학", "005070": "화학",
    "034020": "중공업", "010140": "조선", "329180": "조선", "009540": "조선",
    "015760": "유틸리티", "017670": "통신", "030200": "통신", "033780": "소비재",
    "028260": "건설/지주", "012450": "방산", "352820": "엔터", "066570": "가전",
    "000720": "건설", "006360": "건설", "047040": "건설",
}

NOT_AVAILABLE = "조회 불가"

# ─── 캐싱: 동일 티커 1시간 캐시 ───────────────────────────────────────────
@st.cache_data(ttl=3600, show_spinner=False)
def cached_kr_data(ticker: str) -> dict:
    return get_kr_data(ticker)


@st.cache_data(ttl=3600, show_spinner=False)
def cached_yahoo_data(ticker: str) -> dict:
    return get_yahoo_data(ticker)


# ─── 페이지 설정 ──────────────────────────────────────────────────────────
st.set_page_config(page_title="VIP 포트폴리오 브리핑", page_icon="📊", layout="wide")

# ─── 세션 상태 ────────────────────────────────────────────────────────────
for key, default in [
    ("portfolio", []),
    ("account", {}),  # 예수금, 매매잔고합계
    ("stock_data", {}),
    ("deep_data", {}),  # 상위 3종목 PER 비교, 30일 수급, 1년 차트 PNG
    ("ai_analysis", []),
    ("macro_briefing", {}),
    ("health", {}),
    ("rebalancing", []),
    ("cost_estimate", 0.0),
    ("cost_breakdown", []),
    ("step", 0),  # 0=초기, 1=파싱완료, 2=시세완료, 3=AI완료
    ("error", None),
]:
    st.session_state.setdefault(key, default)


# ─── 사이드바 ─────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("📊 VIP 브리핑")
    st.caption("계좌 이미지 → AI 분석 → 자동 보고서")
    st.divider()

    password = st.text_input(
        "비밀번호",
        type="password",
        placeholder="비밀번호를 입력하세요",
        help="센터 내부 접근 비밀번호 (관리자에게 문의)",
    )
    # API 키는 .env(로컬) 또는 Streamlit Cloud Secrets에서 자동 로드 (사용자에게 노출 안 됨)
    api_key = _get_secret("ANTHROPIC_API_KEY")
    client_name = st.text_input("고객명", value="VIP 고객")
    rm_name = st.text_input("담당 RM", value="담당 매니저")

    st.divider()
    include_macro = st.checkbox(
        "🌐 거시경제 브리핑 포함",
        value=True,
        help="시장 지수 수집 + Claude 분석을 보고서에 추가. 약 +$0.04 비용, +20초 소요.",
    )

    st.divider()
    st.caption("**비용 안내**\nClaude API는 본인 키로 호출되어 본인 계정에 청구됩니다. 1회 분석당 약 $0.20~0.30 (모든 단계 포함).")
    st.caption("**개인정보 안내**\nAPI 키·고객 정보는 세션 메모리에만 머무르며 서버에 저장되지 않습니다. 페이지를 닫으면 즉시 삭제됩니다.")

    st.markdown(
        "<div style='position: fixed; bottom: 12px; left: 16px; "
        "font-size: 11px; color: #9ca3af;'>"
        "제작자 : 유진투자증권 법인전담팀 정현철"
        "</div>",
        unsafe_allow_html=True,
    )


# ─── 메인 ─────────────────────────────────────────────────────────────────
st.title("VIP 포트폴리오 브리핑 시스템")
st.caption(f"오늘 날짜: {datetime.now().strftime('%Y년 %m월 %d일')}")

if password != ACCESS_PASSWORD:
    if password:
        st.error("비밀번호가 일치하지 않습니다.")
    else:
        st.warning("👈 사이드바에 비밀번호를 먼저 입력해 주세요.")
    st.stop()

if not api_key:
    st.error("⚠️ API 키가 .env 파일에 설정되어 있지 않습니다. 관리자에게 문의하세요.")
    st.stop()

# ── STEP 1: 이미지 업로드 ────────────────────────────────────────────────
st.subheader("1. 계좌 이미지 업로드")
uploaded = st.file_uploader(
    "증권앱 계좌잔고 화면 캡처를 올려주세요 (PNG·JPG·WebP)",
    type=["png", "jpg", "jpeg", "webp", "gif"],
)
if uploaded is None:
    st.info("이미지를 업로드하면 분석이 시작됩니다.")
    st.stop()

st.image(uploaded, caption=uploaded.name, width=420)

# ── STEP 2: 종목 추출 + 편집 + 분석 ────────────────────────────────────
st.subheader("2. 종목 추출 및 분석")

# 새 이미지 업로드 감지 — 다른 파일이면 분석 상태 초기화
upload_id = f"{uploaded.name}_{uploaded.size}"
if st.session_state.get("last_upload_id") != upload_id:
    st.session_state.last_upload_id = upload_id
    st.session_state.step = 0
    st.session_state.portfolio = []
    st.session_state.stock_data = {}
    st.session_state.ai_analysis = []
    st.session_state.macro_briefing = {}
    st.session_state.health = {}
    st.session_state.rebalancing = []
    st.session_state.cost_estimate = 0.0
    st.session_state.cost_breakdown = []
    st.session_state.error = None

image_bytes = uploaded.getvalue()
media_type = detect_media_type(uploaded.name)

# ── Phase A: Vision 종목 추출 (step < 1 일 때 버튼 노출) ──
if st.session_state.step < 1:
    if st.button("🔍 종목 추출 시작", type="primary"):
        st.session_state.error = None
        with st.status("이미지에서 종목 추출 중...", expanded=True) as status:
            try:
                size_mb = len(image_bytes) / 1024 / 1024
                st.write(f"이미지 크기: {size_mb:.1f} MB")
                if len(image_bytes) > 3_700_000:
                    st.write("⚠️ 이미지가 커서 Claude API 한도에 맞춰 자동 축소합니다")
                result = parse_portfolio_image(image_bytes, media_type, api_key)
                stocks_raw = result.get("stocks", []) or []
                account = result.get("account", {}) or {}
                st.write(f"✓ {len(stocks_raw)}개 종목 추출")
                if account.get("예수금"):
                    st.write(f"  • 예수금: {int(account['예수금']):,}원")
                if account.get("매매잔고합계"):
                    st.write(f"  • 매매잔고합계: {int(account['매매잔고합계']):,}원")
                portfolio = deduplicate(stocks_raw)
                if len(portfolio) < len(stocks_raw):
                    st.write(f"✓ 중복 합산 → {len(portfolio)}개")

                # 정적 맵에 없는 국내 종목 → 네이버 검색으로 정식 종목명 교정
                unknowns = [
                    h for h in portfolio
                    if not is_overseas_name(h["종목명"])
                    and not name_to_ticker_static(h["종목명"])
                ]
                if unknowns:
                    st.write(f"네이버 검색으로 정식 종목명 확인 중 ({len(unknowns)}개)...")
                    for h in unknowns:
                        orig_name = h["종목명"]
                        ticker, canonical = resolve_kr_via_naver_search(orig_name)
                        if ticker and canonical:
                            h["ticker"] = ticker
                            h["market"] = "KR"
                            if canonical != orig_name:
                                h["종목명"] = canonical
                                st.write(f"  ✓ {orig_name} → {canonical} ({ticker})")
                            else:
                                st.write(f"  ✓ {orig_name} → {ticker}")
                        else:
                            st.write(f"  ✗ {orig_name} → 식별 불가 (편집 표에서 수정 필요)")

                status.update(label=f"종목 추출 완료 ({len(portfolio)}개)", state="complete")
                st.session_state.portfolio = portfolio
                st.session_state.account = account
                st.session_state.step = 1
                st.rerun()
            except Exception as e:
                tb = traceback.format_exc()
                print("=" * 60, file=sys.stderr)
                print("이미지 파싱 실패 — 전체 traceback:", file=sys.stderr)
                print(tb, file=sys.stderr)
                print("=" * 60, file=sys.stderr)
                sys.stderr.flush()
                status.update(label="이미지 파싱 실패", state="error")
                st.write(f"**에러 타입**: `{type(e).__name__}`")
                st.write(f"**에러 메시지**: {e}")
                st.code(tb, language="text")
                st.session_state.error = f"이미지 파싱 실패: {type(e).__name__}: {e}"
                st.stop()

# ── Phase B: 추출된 종목 편집 UI (step >= 1) ──
if st.session_state.step >= 1 and st.session_state.portfolio:
    st.markdown("---")
    st.markdown("**📝 추출된 종목 목록 — 잘못 인식된 종목명이 있으면 직접 수정하세요**")
    st.caption("OCR이 종목명을 잘못 읽을 수 있습니다. 예: 'LIGDI펜스앤' → 'LIG넥스원'. 행 추가/삭제도 가능합니다.")

    df_portfolio = pd.DataFrame(st.session_state.portfolio)
    # 사용자 선호 컬럼 순서: 종목명, 현재가, 잔고수량, 매입가, 평가금액, 평가손익금액, 손익율, 비중
    preferred_cols = ["종목명", "현재가", "잔고수량", "매입가", "평가금액", "평가손익금액", "손익율", "비중"]
    existing_cols = [c for c in preferred_cols if c in df_portfolio.columns]
    extra_cols = [c for c in df_portfolio.columns if c not in preferred_cols]
    df_portfolio = df_portfolio[existing_cols + extra_cols]

    if st.session_state.step == 1:
        # 편집 가능 모드 — data_editor로 모든 셀 수정 가능
        edited_df = st.data_editor(
            df_portfolio,
            use_container_width=True,
            num_rows="dynamic",
            key="portfolio_editor",
        )

        col_a, col_b = st.columns([1, 4])
        if col_a.button("✅ 확인 — 분석 진행", type="primary", use_container_width=True):
            edited_records = edited_df.to_dict("records")
            # 빈 종목명 행 제거
            edited_records = [
                r for r in edited_records
                if r.get("종목명") and str(r["종목명"]).strip()
            ]
            if not edited_records:
                st.error("최소 1개 이상의 종목이 필요합니다.")
            else:
                st.session_state.portfolio = edited_records
                st.session_state.step = 2
                st.rerun()
    else:
        # 분석 진행 후 — 읽기 전용 표시
        st.dataframe(df_portfolio, use_container_width=True, hide_index=True)

# ── Phase C: 나머지 파이프라인 실행 (step == 2) ──
if st.session_state.step == 2:
    portfolio = st.session_state.portfolio

    # 2-2: 정적 맵 기반 티커 매핑
    with st.status("종목명 → 티커 매핑 (정적 맵)...", expanded=True) as status:
        try:
            portfolio, kr_pending, needs_overseas = classify_and_map(portfolio)
            kr_count = sum(1 for h in portfolio if h.get("market") == "KR")
            st.write(f"✓ 정적 맵 즉시 매핑: 국내 {kr_count}개")
            if kr_pending:
                st.write(f"  국내 미매핑 {len(kr_pending)}개 → Claude Haiku로 식별 예정")
            if needs_overseas:
                st.write(f"  해외 후보 {len(needs_overseas)}개 → Claude Haiku로 식별 예정")
            status.update(label="정적 매핑 완료", state="complete")
        except Exception as e:
            status.update(label="티커 매핑 실패", state="error")
            st.session_state.error = f"티커 매핑 실패: {e}"
            st.stop()

    # 2-3: 네이버 통합검색으로 국내 미매핑 종목 식별
    if kr_pending:
        with st.status(f"국내 미매핑 종목 식별 중 ({len(kr_pending)}개) — 네이버 검색...",
                       expanded=True) as status:
            for h in kr_pending:
                name = h["종목명"]
                ticker, canonical = resolve_kr_via_naver_search(name)
                if ticker and canonical:
                    h["ticker"] = ticker
                    h["market"] = "KR"
                    if canonical != name:
                        h["종목명"] = canonical
                        st.write(f"  ✓ {name} → {canonical} ({ticker})")
                    else:
                        st.write(f"  ✓ {name} → {ticker}")
                else:
                    h["ticker"] = None
                    h["market"] = "unknown"
                    st.write(f"  ✗ {name} → 식별 불가")
            status.update(label="국내 미매핑 식별 완료", state="complete")

    # 2-4: 해외 티커 식별
    if needs_overseas:
        with st.status(f"해외 종목 티커 식별 중 ({len(needs_overseas)}개)...", expanded=True) as status:
            for h in needs_overseas:
                name = h["종목명"]
                if is_us_ticker(name.upper()):
                    h["ticker"] = name.upper()
                else:
                    h["ticker"] = identify_ticker(name, api_key)
                h["market"] = "US" if h["ticker"] else "unknown"
                st.write(f"  {name} → {h['ticker'] or '식별 불가'}")
            status.update(label="해외 티커 식별 완료", state="complete")

    # 2-5: 시세·재무 수집
    with st.status("시세·재무 데이터 수집 중...", expanded=True) as status:
        stock_data: dict = {}
        progress = st.progress(0)
        items = [h for h in portfolio if h.get("ticker")]
        for i, h in enumerate(items, 1):
            ticker = h["ticker"]
            try:
                if h.get("market") == "KR":
                    stock_data[ticker] = cached_kr_data(ticker)
                elif h.get("market") == "US":
                    stock_data[ticker] = cached_yahoo_data(ticker)
                st.write(f"  ✓ {h['종목명']} ({ticker})")
            except Exception as e:
                st.write(f"  ✗ {h['종목명']} ({ticker}): {e}")
            progress.progress(i / len(items))
        status.update(label=f"시세 수집 완료 ({len(stock_data)}개)", state="complete")

    # 2-5b: 심층 데이터 수집 (상위 3종목 — PER 역사/업종 비교, 30일 수급, 1년 차트)
    with st.status("상위 3종목 심층 데이터 수집 중 (PER·수급·차트)...", expanded=True) as status:
        deep_data: dict = {}
        sorted_top = sorted(portfolio, key=lambda h: h.get("비중", 0), reverse=True)[:3]
        for h in sorted_top:
            ticker = h.get("ticker")
            market = h.get("market", "KR")
            if not ticker:
                continue
            d = stock_data.get(ticker, {}) or {}
            nf = d.get("naver_finance", {}) or {}
            cur_per = nf.get("per")
            sector = SECTOR_MAP.get(ticker, "기타")
            per_cmp = get_per_comparison(ticker, cur_per, sector)
            flow = fetch_30day_flow(ticker) if market == "KR" else None
            chart_png = generate_price_chart(ticker, market)
            deep_data[ticker] = {
                "per_compare": per_cmp,
                "flow": flow,
                "chart_png": chart_png,
            }
            bits = []
            if per_cmp.get("avg_5y"):
                bits.append(f"PER 5y평균 {per_cmp['avg_5y']:.1f}")
            if flow:
                bits.append("30일 수급 ✓")
            if chart_png:
                bits.append("1년 차트 ✓")
            st.write(f"  ✓ {h['종목명']} — {', '.join(bits) if bits else '데이터 부족'}")
        status.update(label=f"심층 데이터 완료 ({len(deep_data)}개)", state="complete")

    # 2-6: AI 심층 분석 (상위 3)
    with st.status("AI 심층 분석 중 (Claude Sonnet)...", expanded=True):
        try:
            ai_results = analyze_top_holdings(
                portfolio, stock_data, api_key, top_n=3, deep_data=deep_data
            )
            st.write(f"✓ {len(ai_results)}개 종목 분석 완료")
        except Exception as e:
            st.warning(f"AI 분석 실패 — 보고서는 분석 없이 생성됩니다: {e}")
            ai_results = []

    # 2-7: 거시경제 브리핑 (사이드바 옵션에 따라)
    if include_macro:
        with st.status("거시경제 브리핑 생성 중 (yfinance + Claude)...", expanded=True) as status:
            try:
                indices = fetch_indices()
                st.write(f"✓ 주요 지수 {len(indices)}개 수집")
                macro = generate_macro_briefing(indices, portfolio, api_key)
                if macro.get("headline"):
                    st.write(f"  • {macro['headline']}")
                status.update(label="거시 브리핑 완료", state="complete")
            except Exception as e:
                st.warning(f"거시 브리핑 실패 (보고서에서 제외): {e}")
                macro = {}
    else:
        macro = {}
        st.info("거시경제 브리핑은 사이드바에서 비활성화되어 생략되었습니다.")

    # 2-8: 포트폴리오 건강 진단
    with st.status("포트폴리오 건강 진단 중...", expanded=True) as status:
        health = diagnose_health(portfolio, SECTOR_MAP)
        if health:
            conc = health.get("concentration", {})
            sect = health.get("sector", {})
            alpha = health.get("alpha", {})
            st.write(f"✓ 집중도: {conc.get('verdict', '-')} (상위 3종목 {conc.get('top3_weight', 0):.1f}%)")
            st.write(f"✓ 섹터 편중: {sect.get('verdict', '-')} (최대 {sect.get('max_sector', '-')} {sect.get('max_sector_weight', 0):.1f}%)")
            if alpha.get("alpha") is not None:
                st.write(f"✓ 알파(vs KOSPI): {alpha['alpha']:+.2f}%p")
        status.update(label="건강 진단 완료", state="complete")

    # 2-9: 리밸런싱 액션 생성
    with st.status("리밸런싱 액션 생성 중 (Claude Sonnet)...", expanded=True) as status:
        try:
            rebalancing_actions = generate_rebalancing(portfolio, ai_results, health, macro, api_key)
            st.write(f"✓ 리밸런싱 액션 {len(rebalancing_actions)}개 생성")
            status.update(label="리밸런싱 완료", state="complete")
        except Exception as e:
            st.warning(f"리밸런싱 생성 실패: {e}")
            rebalancing_actions = []

    # 비용 추정 (단계별 호출 유형 기준 — 실제 ±20% 변동 가능)
    cost_breakdown = [("이미지 파싱 (Claude Sonnet Vision)", 0.04)]
    overseas_count = sum(1 for h in portfolio if h.get("market") == "US")
    if overseas_count:
        cost_breakdown.append(
            (f"해외 티커 식별 {overseas_count}회 (Claude Haiku)", overseas_count * 0.001)
        )
    cost_breakdown.append(("AI 심층 분석 상위 3종목 (Claude Sonnet)", 0.15))
    if include_macro:
        cost_breakdown.append(("거시경제 브리핑 (Claude Sonnet)", 0.04))
    cost_breakdown.append(("리밸런싱 액션 제안 (Claude Sonnet)", 0.05))
    cost_total = sum(c for _, c in cost_breakdown)

    st.session_state.portfolio = portfolio
    st.session_state.stock_data = stock_data
    st.session_state.deep_data = deep_data
    st.session_state.ai_analysis = ai_results
    st.session_state.macro_briefing = macro
    st.session_state.health = health
    st.session_state.rebalancing = rebalancing_actions
    st.session_state.cost_estimate = cost_total
    st.session_state.cost_breakdown = cost_breakdown
    st.session_state.step = 3
    st.success(f"✅ 전체 파이프라인 완료 — 예상 API 비용 약 ${cost_total:.2f}. 아래에서 결과를 확인하세요.")
    st.rerun()

# ── STEP 3: 결과 표시 ────────────────────────────────────────────────────
if st.session_state.error:
    st.error(st.session_state.error)

if st.session_state.step < 3:
    st.stop()

portfolio = st.session_state.portfolio
stock_data = st.session_state.stock_data
ai_analysis = st.session_state.ai_analysis

st.divider()
st.subheader("3. 분석 결과")

# 상위 통계
sorted_p = sorted(portfolio, key=lambda h: h.get("비중", 0), reverse=True)
total_ev = sum(h.get("평가금액") or 0 for h in portfolio)
pnl_arr = [h for h in portfolio if h.get("손익율") is not None]
avg_pnl = sum(h["손익율"] for h in pnl_arr) / len(pnl_arr) if pnl_arr else None

account = st.session_state.get("account", {}) or {}
cash = account.get("예수금")
total_balance = account.get("매매잔고합계")

m1, m2, m3 = st.columns(3)
m1.metric("총 종목 수", f"{len(portfolio)}개")
m2.metric("주식 평가금액", f"{total_ev:,.0f}원" if total_ev else "-")
m3.metric("예수금", f"{int(cash):,}원" if isinstance(cash, (int, float)) else "-")

m4, m5, m6 = st.columns(3)
m4.metric("매매잔고합계", f"{int(total_balance):,}원" if isinstance(total_balance, (int, float)) else "-")
m5.metric("평균 손익율", f"{avg_pnl:+.2f}%" if avg_pnl is not None else "-")
m6.metric("최대 비중", sorted_p[0]["종목명"] if sorted_p else "-")

# 종목 테이블
rows = []
for i, h in enumerate(sorted_p, 1):
    d = stock_data.get(h.get("ticker") or "", {}) or {}
    krx = d.get("krx", {}) or {}
    nf = d.get("naver_finance", {}) or {}
    price = krx.get("current_price")
    target = nf.get("analyst_target_price")
    buy = h.get("매입가")
    pnl = h.get("손익율")
    # 이미지에서 손익율 안 나왔으면 매입가/현재가로 계산
    if pnl is None and isinstance(buy, (int, float)) and isinstance(price, (int, float)) and buy:
        pnl = (price - buy) / buy * 100
    foreign = krx.get("foreign_ownership_ratio")
    eval_amount = h.get("평가금액")
    eval_pnl = h.get("평가손익금액")
    rows.append({
        "#": i,
        "종목명": h["종목명"],
        "티커": h.get("ticker") or "-",
        "비중": f"{h.get('비중',0):.1f}%",
        "현재가": f"{int(price):,}" if isinstance(price, (int, float)) and price != NOT_AVAILABLE else "-",
        "잔고수량": h.get("잔고수량") if h.get("잔고수량") is not None else "-",
        "매입가": f"{int(buy):,}" if isinstance(buy, (int, float)) else "-",
        "평가금액": f"{int(eval_amount):,}" if isinstance(eval_amount, (int, float)) else "-",
        "평가손익금액": f"{int(eval_pnl):+,}" if isinstance(eval_pnl, (int, float)) else "-",
        "손익율": f"{pnl:+.2f}%" if pnl is not None else "-",
        "PER": nf.get("per", "-"),
        "PBR": nf.get("pbr", "-"),
        "외국인비율": f"{foreign}%" if isinstance(foreign, (int, float)) else "-",
        "목표주가": f"{int(target):,}" if isinstance(target, (int, float)) else "-",
    })

st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

# AI 분석
if ai_analysis:
    st.subheader("4. AI 심층 분석 (상위 3개)")
    for i, item in enumerate(ai_analysis, 1):
        with st.expander(f"{i}위. {item.get('name', '?')}", expanded=(i == 1)):
            sections = [
                ("📊 산업 내 경쟁 포지션", "competitive_position"),
                ("💰 최근 실적과 가이던스", "recent_performance"),
                ("📈 밸류에이션 분석", "valuation"),
                ("🚀 향후 모멘텀 동인", "catalysts"),
            ]
            for label, key in sections:
                if item.get(key):
                    st.markdown(f"**{label}**")
                    st.write(item[key])
            if item.get("risks"):
                st.markdown("**⚠️ 주요 리스크**")
                for r in item["risks"]:
                    st.markdown(f"- {r}")
            if item.get("strategy_short") or item.get("strategy_mid"):
                st.markdown("**🎯 투자 전략**")
                if item.get("strategy_short"):
                    st.markdown(f"- **단기**: {item['strategy_short']}")
                if item.get("strategy_mid"):
                    st.markdown(f"- **중기**: {item['strategy_mid']}")

# ── API 비용 표시 ─────────────────────────────────────────────────────
if st.session_state.cost_estimate:
    st.divider()
    cost_total = st.session_state.cost_estimate
    cost_breakdown = st.session_state.cost_breakdown
    with st.expander(f"💰 이번 분석 예상 API 비용: 약 ${cost_total:.2f}", expanded=False):
        st.caption("입력/출력 토큰 수에 따라 실제 비용은 ±20% 변동될 수 있습니다.")
        for label, cost in cost_breakdown:
            st.write(f"- {label}: ${cost:.3f}")
        st.markdown(f"**합계: 약 ${cost_total:.2f}**")

# ── STEP 4: 보고서 다운로드 ──────────────────────────────────────────────
st.divider()
st.subheader("5. 보고서 다운로드")
st.caption("DOCX 파일은 PDF 톤(크림/에스프레소 에디토리얼)이 그대로 적용됩니다.")

date_str = datetime.now().strftime("%Y%m%d")

c1, c2 = st.columns(2)
with c1:
    if st.button("📄 요약보고서 생성", use_container_width=True):
        with st.spinner("DOCX 생성 중..."):
            data = build_summary(
                portfolio, stock_data, ai_analysis, SECTOR_MAP, client_name, rm_name,
                macro=st.session_state.macro_briefing,
                health=st.session_state.health,
                rebalancing=st.session_state.rebalancing,
                account=st.session_state.account,
                deep_data=st.session_state.deep_data,
            )
        st.download_button(
            "⬇️ 요약보고서 다운로드 (.docx)",
            data=data,
            file_name=f"{client_name}_요약보고서_{date_str}.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            use_container_width=True,
            type="primary",
        )

with c2:
    if st.button("📋 상세보고서 생성", use_container_width=True):
        with st.spinner("DOCX 생성 중..."):
            data = build_detail(
                portfolio, stock_data, ai_analysis, SECTOR_MAP, client_name, rm_name,
                macro=st.session_state.macro_briefing,
                health=st.session_state.health,
                rebalancing=st.session_state.rebalancing,
                account=st.session_state.account,
                deep_data=st.session_state.deep_data,
            )
        st.download_button(
            "⬇️ 상세보고서 다운로드 (.docx)",
            data=data,
            file_name=f"{client_name}_상세보고서_{date_str}.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            use_container_width=True,
            type="primary",
        )

# ── STEP 5: 고객 발송용 메일 템플릿 ─────────────────────────────────────
st.divider()
st.subheader("6. 📧 고객 발송용 메일 템플릿")
st.caption("아래 제목·본문을 회사 메일 작성창에 복사·붙여넣기하시고, "
           "위에서 다운로드한 보고서 DOCX를 첨부하여 발송하세요.")

_email = build_email(
    client_name=client_name,
    rm_name=rm_name,
    portfolio=portfolio,
    ai_analysis=ai_analysis,
    account=st.session_state.get("account", {}),
    report_filename=f"{client_name}_상세보고서_{date_str}.docx",
)

st.text_input("제목", value=_email["subject"], key="email_subject_field")
st.text_area("본문 (복사용)", value=_email["body"],
             height=480, key="email_body_field")
