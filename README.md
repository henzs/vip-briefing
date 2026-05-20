# VIP 포트폴리오 브리핑 — Streamlit 웹앱

증권앱 계좌잔고 이미지를 업로드하면 Claude Vision으로 종목을 추출하고, KRX·네이버금융·yfinance에서 시세·재무 데이터를 모은 뒤, Claude Sonnet으로 상위 3종목 심층 분석을 수행해 에디토리얼 톤의 DOCX 보고서를 생성합니다.

## 구조

```
streamlit_app/
├── app.py                  # Streamlit UI 오케스트레이션
├── image_parser.py         # Claude Vision 종목 추출
├── portfolio.py            # 중복 합산 + 종목명→티커 매핑
├── fetcher_kr.py           # KRX (pykrx) + 네이버 금융 + FnGuide
├── fetcher_overseas.py     # Claude Haiku 티커 식별 + yfinance
├── ai_analysis.py          # 상위 3종목 심층 분석 (Claude Sonnet)
├── report_builder.py       # DOCX 보고서 (python-docx, 에디토리얼 톤)
├── requirements.txt
└── README.md
```

## 로컬 실행

```bash
cd streamlit_app
python -m venv venv
# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate

pip install -r requirements.txt
streamlit run app.py
```

브라우저가 자동으로 `http://localhost:8501`을 열며, 사이드바에 본인의 Anthropic API 키를 입력한 뒤 계좌 이미지를 업로드합니다.

## API 키 발급
[console.anthropic.com](https://console.anthropic.com/) 에서 발급. 입력값은 **세션 메모리에만** 머무르며 페이지를 닫으면 즉시 사라집니다 (서버에 저장 안 됨).

**비용 예상**: 1회 분석당 약 $0.03 ~ $0.10 (이미지 파싱 + 상위 3종목 심층 분석 포함).

## 클라우드 배포 (Streamlit Community Cloud)

1. 이 폴더를 GitHub 저장소에 푸시 (예: `vip-briefing-streamlit`)
2. [share.streamlit.io](https://share.streamlit.io/) 접속 → GitHub 연결 → 리포지토리 선택
3. **Main file path**에 `app.py` 지정
4. **Python version**은 3.10 이상 권장
5. Deploy 클릭

배포 후 모든 방문자가 자신의 API 키를 입력해 사용할 수 있습니다 — 운영자는 호스팅 비용만 부담하고 API 비용은 각 사용자가 자기 계정에 청구됩니다.

### 주의: 클라우드 배포 시 캐시 동작
- `@st.cache_data(ttl=3600)`로 시세 데이터는 1시간 캐싱됩니다.
- pykrx의 종목명→티커 전체 맵은 첫 호출 시 KRX에서 다운로드(약 5~15초 소요) 후 메모리에 보관됩니다. 워커 재시작 시 다시 받아옵니다.

## 동작 흐름

1. **이미지 업로드** — 사용자가 증권앱 계좌잔고 캡처 업로드
2. **종목 추출** — Claude Vision (Sonnet 4.6)이 JSON으로 종목·비중·평가금액 추출
3. **중복 합산** — (일반)/(담보)/(신용) 등 괄호 정규화 후 같은 종목 합산
4. **티커 매핑** — 한글 포함 → 정적 맵 + KRX 전종목 매핑 / 영문 → 해외 후보로 분류
5. **해외 식별** — 영문 종목은 Claude Haiku에 Yahoo 티커 질의
6. **시세·재무** — 국내는 pykrx + 네이버금융 + FnGuide / 해외는 yfinance
7. **AI 분석** — 상위 3종목에 대해 Claude Sonnet이 4가지 관점 분석 (밸류에이션 / 기술적 / 목표가 괴리율 / 투자의견)
8. **DOCX 다운로드** — 요약(2페이지) / 상세(5페이지) — 크림/에스프레소 에디토리얼 톤

## 알려진 제약
- **Streamlit Community Cloud 리소스**: 1GB RAM. 동시 사용자가 많으면 KRX 호출이 지연되거나 yfinance가 rate limit에 걸릴 수 있습니다.
- **네이버 금융·FnGuide 스크래핑**: 사이트 구조가 바뀌면 일부 필드가 "조회 불가"로 표시될 수 있습니다.
- **Korean fonts in DOCX**: 보고서는 Windows 기본 폰트(맑은 고딕·바탕)를 가정합니다. macOS·Linux에서 보기에는 Word가 자동 대체 폰트를 사용합니다.

## 기존 시스템과의 차이
- 이전: 브라우저에서 직접 Claude API 호출 + `localhost:8000` data-server FastAPI
- 현재: Streamlit 단일 프로세스로 모든 처리 — 별도 서버 필요 없음
- 디자인: 화면은 Streamlit 기본 UI, DOCX 다운로드만 에디토리얼 톤 유지
