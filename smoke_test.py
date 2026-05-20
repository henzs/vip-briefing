"""report_builder.py 단독 스모크 테스트.
모의 데이터로 두 DOCX를 생성해 정상 출력 여부 확인."""
from pathlib import Path

from report_builder import build_detail, build_summary

# 모의 데이터 (Node.js 테스트와 동일 구조)
portfolio = [
    {"종목명": "삼성전자",       "ticker": "005930", "market": "KR", "비중": 28.5, "수량": 100, "평가금액": 7500000, "수익률": 12.3},
    {"종목명": "SK하이닉스",     "ticker": "000660", "market": "KR", "비중": 18.2, "수량": 30,  "평가금액": 4800000, "수익률": 24.7},
    {"종목명": "LG에너지솔루션", "ticker": "373220", "market": "KR", "비중": 14.1, "수량": 10,  "평가금액": 3700000, "수익률": -5.2},
    {"종목명": "NAVER",          "ticker": "035420", "market": "KR", "비중": 12.8, "수량": 25,  "평가금액": 3400000, "수익률": 8.6},
    {"종목명": "카카오",         "ticker": "035720", "market": "KR", "비중": 10.4, "수량": 75,  "평가금액": 2750000, "수익률": -8.1},
    {"종목명": "현대차",         "ticker": "005380", "market": "KR", "비중": 8.5,  "수량": 12,  "평가금액": 2250000, "수익률": 15.8},
    {"종목명": "셀트리온",       "ticker": "068270", "market": "KR", "비중": 7.5,  "수량": 20,  "평가금액": 1980000, "수익률": 3.4},
]

stock_data = {
    "005930": {"krx": {"current_price": 75000, "market_cap": 4476000000000000, "week52_high": 88800, "week52_low": 68500, "foreign_ownership_ratio": 54.2},
               "naver_finance": {"per": "12.4", "pbr": "1.32", "eps": "6,050", "bps": "56,800", "dividend_yield": "1.85%", "analyst_target_price": 90000}},
    "000660": {"krx": {"current_price": 160000, "market_cap": 116000000000000, "week52_high": 174800, "week52_low": 105000, "foreign_ownership_ratio": 52.8},
               "naver_finance": {"per": "18.7", "pbr": "2.05", "eps": "8,556", "bps": "78,000", "dividend_yield": "0.62%", "analyst_target_price": 210000}},
    "373220": {"krx": {"current_price": 370000, "market_cap": 86600000000000, "week52_high": 525000, "week52_low": 330000, "foreign_ownership_ratio": 4.1},
               "naver_finance": {"per": "85.3", "pbr": "3.45", "eps": "4,335", "bps": "107,000", "dividend_yield": "-", "analyst_target_price": 480000}},
}

ai_analysis = [
    {"종목명": "삼성전자", "분석": "HBM 메모리 수요 견조 지속, AI 데이터센터향 매출 비중 확대로 2026년 영업이익 추가 성장 여력 보유.\n파운드리 부문 GAA 공정 안정화 진행 중.\n자사주 매입 정책 지속으로 주주환원 강화 흐름.\n단기 리스크: 환율 변동성 및 중국 수요 둔화 영향 점검 필요."},
    {"종목명": "SK하이닉스", "분석": "HBM3E 12단 양산 본격화로 엔비디아 향 점유율 60% 이상 유지.\nDRAM 가격 상승 사이클 진입, 영업이익 컨센서스 상향.\n낸드 부문 적자 축소 진행 중.\n주의: 메모리 사이클 정점 신호 발생 시 밸류에이션 부담."},
    {"종목명": "LG에너지솔루션", "분석": "전기차 수요 둔화 영향 단기 실적 부진.\n4680 셀 양산 안정화 진행.\nESS 사업 비중 확대로 EV 의존도 분산.\n분기 실적 턴어라운드 확인 시 재평가 여지."},
]

SECTOR_MAP = {
    "005930": "반도체", "000660": "반도체", "373220": "2차전지",
    "035420": "IT플랫폼", "035720": "IT플랫폼", "005380": "자동차", "068270": "바이오",
}

out_dir = Path(__file__).parent / "test_output"
out_dir.mkdir(exist_ok=True)

summary_bytes = build_summary(portfolio, stock_data, ai_analysis, SECTOR_MAP, "김VIP", "박매니저")
(out_dir / "김VIP_요약보고서_python.docx").write_bytes(summary_bytes)

detail_bytes = build_detail(portfolio, stock_data, ai_analysis, SECTOR_MAP, "김VIP", "박매니저")
(out_dir / "김VIP_상세보고서_python.docx").write_bytes(detail_bytes)

print(f"[OK] summary docx: {len(summary_bytes):,} bytes")
print(f"[OK] detail  docx: {len(detail_bytes):,} bytes")
print(f"     output dir : {out_dir}")
