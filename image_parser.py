"""계좌잔고 이미지를 Claude Vision으로 분석해 보유 종목 리스트를 추출."""
import base64
import json
import re
from io import BytesIO

import anthropic
from PIL import Image


def _extract_json(raw: str) -> str:
    """Claude 응답에서 JSON 부분만 추출. 앞뒤 설명/계산과정/마크다운 펜스 모두 처리."""
    raw = raw.strip()
    # 1) ```json ... ``` 또는 ``` ... ``` 코드 펜스 추출
    fence = re.search(r"```(?:json)?\s*(.*?)```", raw, re.DOTALL)
    if fence:
        candidate = fence.group(1).strip()
        if candidate.startswith("[") or candidate.startswith("{"):
            return candidate
    # 2) 첫 [ 부터 마지막 ] 까지 (배열)
    start, end = raw.find("["), raw.rfind("]")
    if start >= 0 and end > start:
        return raw[start:end + 1]
    # 3) 첫 { 부터 마지막 } 까지 (객체)
    start, end = raw.find("{"), raw.rfind("}")
    if start >= 0 and end > start:
        return raw[start:end + 1]
    return raw

# Claude API의 이미지 크기 제한은 base64 인코딩 후 5MB.
# base64는 원본을 약 4/3배로 부풀리므로, 원본 한도는 5MB × 3/4 ≈ 3.93MB.
# 안전 여유를 두어 3.7MB로 설정 (base64 후 약 4.93MB).
MAX_IMAGE_BYTES = 3_700_000

PROMPT = """이 이미지는 증권사 HTS의 잔고손익평가 화면이야. 보유 종목별 행만 정확히 추출해줘.

규칙:
1. 종목 행만 추출. 상단의 예수금/출금가능액/평가금액합/평가손익합 같은 합계/요약 영역은 무시.
2. 종목명은 이미지에 보이는 텍스트 그대로 정확히. 절대 추측·변경 금지.
   - 한글 종목명: 글자 하나하나 정확히 (예: 동아엘텍, 삼성전자)
   - 영문 티커: 대문자 그대로 (예: PLTU, TSLL, TSLA)
3. 종목명에서 (일반), (담보), (신용) 등 괄호 표시는 제거.
4. 같은 종목이 여러 줄이면 각각 별도 항목으로 추출 (합산은 코드에서 처리).
5. 다음 필드를 정확히 해당 컬럼 라벨의 값만 읽어서 추출 (보이지 않으면 생략):
   - 현재가: '현재가' 컬럼의 숫자값 (콤마 제거)
   - 잔고수량: '잔고수량' 컬럼 (없으면 '매매잔고' 또는 '보유수량')
   - 매입가: '매입가' 컬럼 (없으면 '매수평단', '평균매입가', '평균단가')
   - 평가금액: '평가금액' 컬럼만. (매입금액/매입원가/평가손익금액과 절대 혼동 금지)
   - 평가손익금액: '평가손익금액' 또는 '평가손익' 컬럼. 부호 포함 (음수면 -로)
   - 손익율: '손익율' 또는 '수익률' 컬럼. % 단위, 부호 포함 (예: +8.40, -10.40)
6. 비중(%)은 이미지에 없으면 평가금액 기준 전체 합 대비 % 계산.
7. 결과는 반드시 아래 JSON 형식, 키 순서까지 정확히 일치하게 반환. 다른 텍스트 일절 금지.

[
  {"종목명": "현대차", "현재가": 591000, "잔고수량": 100, "매입가": 545217, "평가금액": 59100000, "평가손익금액": 4578260, "손익율": 8.40, "비중": 7.6},
  {"종목명": "삼성전자", "현재가": 270500, "잔고수량": 150, "매입가": 262526, "평가금액": 40575000, "평가손익금액": 1196063, "손익율": 3.04, "비중": 5.2}
]
필드 중 보이지 않는 것은 생략 가능. 추측 절대 금지."""


def _compress_if_needed(image_bytes: bytes, media_type: str) -> tuple[bytes, str]:
    """5MB 초과 시 PIL로 축소. (압축된 바이트, 새 media_type) 반환.

    JPEG 품질·치수를 단계적으로 낮춰가며 한도 안에 들어올 때까지 시도.
    """
    if len(image_bytes) <= MAX_IMAGE_BYTES:
        return image_bytes, media_type

    img = Image.open(BytesIO(image_bytes))
    if img.mode in ("RGBA", "P", "LA"):
        img = img.convert("RGB")

    # 1차: 원 해상도 유지, JPEG 품질만 낮춤
    for quality in (90, 80, 70):
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        data = buf.getvalue()
        if len(data) <= MAX_IMAGE_BYTES:
            return data, "image/jpeg"

    # 2차: 해상도 축소 + 품질 조정
    for scale in (0.85, 0.7, 0.55, 0.4):
        new_size = (int(img.width * scale), int(img.height * scale))
        resized = img.resize(new_size, Image.LANCZOS)
        for quality in (85, 75, 65):
            buf = BytesIO()
            resized.save(buf, format="JPEG", quality=quality, optimize=True)
            data = buf.getvalue()
            if len(data) <= MAX_IMAGE_BYTES:
                return data, "image/jpeg"

    # 3차 (최후): 1200px 썸네일
    img.thumbnail((1200, 1200), Image.LANCZOS)
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=70, optimize=True)
    return buf.getvalue(), "image/jpeg"


def parse_portfolio_image(image_bytes: bytes, media_type: str, api_key: str) -> list[dict]:
    """이미지 바이트를 받아 종목 리스트 반환. 실패 시 RuntimeError 발생.

    Claude API의 5MB 제한을 초과하면 자동으로 PIL 축소.
    """
    image_bytes, media_type = _compress_if_needed(image_bytes, media_type)
    image_data = base64.standard_b64encode(image_bytes).decode("utf-8")

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": media_type, "data": image_data},
                },
                {"type": "text", "text": PROMPT},
            ],
        }],
    )

    # 응답에서 JSON 부분만 추출 (앞뒤 설명·계산과정·마크다운 펜스 모두 처리)
    raw = response.content[0].text
    clean = _extract_json(raw)

    try:
        return json.loads(clean)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"JSON 파싱 실패: {e}\n원본 응답:\n{raw}") from e


def detect_media_type(filename: str) -> str:
    """파일명 확장자로 MIME 타입 판별."""
    suffix = filename.lower().rsplit(".", 1)[-1] if "." in filename else "png"
    return {
        "jpg": "image/jpeg", "jpeg": "image/jpeg",
        "png": "image/png", "gif": "image/gif", "webp": "image/webp",
    }.get(suffix, "image/png")
