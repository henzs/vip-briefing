"""샘플 포트폴리오로 상세보고서 시연 생성.

테스트용. 실제 앱과 동일한 파이프라인을 합성 포트폴리오로 실행.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

from datetime import datetime

from ai_analysis import analyze_top_holdings
from fetcher_kr import get_stock_data as get_kr_data
from flow_data import fetch_30day_flow
from macro_briefing import fetch_indices, generate_macro_briefing
from portfolio_health import diagnose_health
from rebalancing import generate_rebalancing
from report_builder import build_detail
from stock_chart import generate_price_chart
from valuation_compare import get_per_comparison

API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
if not API_KEY:
    print("ANTHROPIC_API_KEY가 .env에 없음")
    sys.exit(1)

SECTOR_MAP = {
    "005930": "반도체",
    "005380": "자동차",
    "088130": "전자부품",
}

print("=" * 60)
print("샘플 보고서 생성")
print("  - 삼성전자 100주 @ 250,000원")
print("  - 현대차 100주 @ 700,000원")
print("  - 동아엘텍 100주 @ 10,000원")
print("=" * 60)

# Step 1: 포트폴리오 (매입 정보)
portfolio = [
    {"종목명": "삼성전자", "ticker": "005930", "market": "KR",
     "잔고수량": 100, "매입가": 250000},
    {"종목명": "현대차", "ticker": "005380", "market": "KR",
     "잔고수량": 100, "매입가": 700000},
    {"종목명": "동아엘텍", "ticker": "088130", "market": "KR",
     "잔고수량": 100, "매입가": 10000},
]

# Step 2: 시세·재무 수집
print("\n[1/8] 시세·재무 수집 (KRX + 네이버금융)...")
stock_data = {}
for h in portfolio:
    ticker = h["ticker"]
    try:
        stock_data[ticker] = get_kr_data(ticker)
        krx = stock_data[ticker].get("krx", {})
        print(f"  ✓ {h['종목명']} 현재가 {krx.get('current_price', 0):,}원")
    except Exception as e:
        print(f"  ✗ {h['종목명']}: {e}")
        stock_data[ticker] = {"krx": {}, "naver_finance": {}}

# Step 3: 평가금액·손익율·비중 계산
print("\n[2/8] 손익 계산...")
total_ev = 0
for h in portfolio:
    ticker = h["ticker"]
    krx = stock_data[ticker].get("krx", {})
    cur_price = krx.get("current_price", 0)
    if not isinstance(cur_price, (int, float)) or cur_price <= 0:
        cur_price = h["매입가"]
    h["현재가"] = cur_price
    h["평가금액"] = int(cur_price * h["잔고수량"])
    h["평가손익금액"] = int((cur_price - h["매입가"]) * h["잔고수량"])
    if h["매입가"] > 0:
        h["손익율"] = round((cur_price - h["매입가"]) / h["매입가"] * 100, 2)
    total_ev += h["평가금액"]

for h in portfolio:
    h["비중"] = round(h["평가금액"] / total_ev * 100, 2) if total_ev else 0
    print(f"  {h['종목명']}: 평가 {h['평가금액']:,}원, 손익율 {h['손익율']:+.2f}%, 비중 {h['비중']:.1f}%")

# Step 4: 심층 데이터 (PER 비교 / 30일 수급 / 1년 차트)
print("\n[3/8] 심층 데이터 수집 (PER · 수급 · 차트)...")
deep_data = {}
for h in portfolio:
    ticker = h["ticker"]
    sector = SECTOR_MAP.get(ticker, "기타")
    nf = stock_data[ticker].get("naver_finance", {})
    cur_per = nf.get("per")
    per_cmp = get_per_comparison(ticker, cur_per, sector)
    flow = fetch_30day_flow(ticker)
    chart = generate_price_chart(ticker, "KR")
    deep_data[ticker] = {
        "per_compare": per_cmp,
        "flow": flow,
        "chart_png": chart,
    }
    bits = []
    if per_cmp.get("avg_5y"):
        bits.append(f"PER 5y평균 {per_cmp['avg_5y']:.1f}")
    if flow:
        bits.append("수급 ✓")
    if chart:
        bits.append("차트 ✓")
    print(f"  {h['종목명']}: {', '.join(bits)}")

# Step 5: AI 심층 분석
print("\n[4/8] AI 심층 분석 (Claude Sonnet 4.6)...")
try:
    ai_results = analyze_top_holdings(
        portfolio, stock_data, API_KEY, top_n=3, deep_data=deep_data
    )
    print(f"  ✓ {len(ai_results)}개 종목 분석 완료")
except Exception as e:
    print(f"  ✗ AI 분석 실패: {e}")
    ai_results = []

# Step 6: 거시 브리핑
print("\n[5/8] 거시경제 브리핑...")
try:
    indices = fetch_indices()
    macro = generate_macro_briefing(indices, portfolio, API_KEY)
    print(f"  ✓ 지수 {len(indices)}개 + Claude 분석")
    if macro.get("headline"):
        print(f"    {macro['headline']}")
except Exception as e:
    print(f"  ✗ 거시 브리핑 실패: {e}")
    macro = {}

# Step 7: 건강 진단
print("\n[6/8] 포트폴리오 건강 진단...")
health = diagnose_health(portfolio, SECTOR_MAP)
if health:
    conc = health.get("concentration", {})
    sect = health.get("sector", {})
    print(f"  집중도: {conc.get('verdict')} (상위 3종목 {conc.get('top3_weight'):.1f}%)")
    print(f"  최대 섹터: {sect.get('max_sector')} {sect.get('max_sector_weight'):.1f}%")

# Step 8: 리밸런싱
print("\n[7/8] 리밸런싱 액션 생성...")
try:
    rebalancing = generate_rebalancing(portfolio, ai_results, health, macro, API_KEY)
    print(f"  ✓ {len(rebalancing)}개 액션")
except Exception as e:
    print(f"  ✗ 리밸런싱 실패: {e}")
    rebalancing = []

# Step 9: 보고서 생성
print("\n[8/8] DOCX 보고서 생성...")
account = {"예수금": 0, "매매잔고합계": int(total_ev)}
data = build_detail(
    portfolio, stock_data, ai_results, SECTOR_MAP,
    "샘플고객", "정현철",
    macro=macro, health=health, rebalancing=rebalancing,
    account=account, deep_data=deep_data,
)

output_dir = os.path.join(os.path.dirname(__file__), "test_output")
os.makedirs(output_dir, exist_ok=True)
output_path = os.path.join(
    output_dir,
    f"샘플고객_상세보고서_시연_{datetime.now().strftime('%Y%m%d_%H%M')}.docx"
)
with open(output_path, "wb") as f:
    f.write(data)

print(f"\n{'=' * 60}")
print(f"✓ 완료: {output_path}")
print(f"  파일 크기: {len(data)/1024:.1f} KB")
print("=" * 60)
