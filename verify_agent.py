"""
3번 워크플로우: 교차 검증

1번은 '결제금액' 하나를 읽고, 3번은 다른 방법으로 읽는다:
  - 합계금액: 영수증의 '합계' 줄에 적힌 최종 금액
  - 품목금액: 품목마다 적힌 금액 목록
  - 거래일자
코드(normalize.compare_verify)가 두 가지를 확인한다:
  1) 품목 금액을 더한 값 = 3번이 읽은 합계   (영수증 스스로의 검산)
  2) 3번이 읽은 합계·날짜 = 1번이 읽은 금액·날짜 (교차검증)
"""

import config
from agent_client import run_agent, run_agent_mock
from normalize import normalize_extract, parse_amount


def verify_enabled() -> bool:
    return bool(config.VERIFY_AGENT_ID)


def _find_items(obj):
    """'품목금액' 목록을 찾는다. (키 이름에 '품목'과 '금액'이 같이 들어간 항목)"""
    if isinstance(obj, dict):
        for k, v in obj.items():
            key = str(k).replace(" ", "").lower()
            if ("품목" in key and "금액" in key) or key in ("itemamounts", "item_amounts", "items"):
                return v
        for v in obj.values():
            if isinstance(v, dict):
                found = _find_items(v)
                if found is not None:
                    return found
    return None


def parse_item_amounts(v) -> list:
    """[16000, "2,000원", [3200]] 처럼 섞여 와도 숫자 목록으로 만든다."""
    out = []
    if isinstance(v, dict):
        v = v.get("value", list(v.values()))
    if isinstance(v, (list, tuple)):
        for i in v:
            out.extend(parse_item_amounts(i))
    else:
        amount = parse_amount(v)
        if amount is not None:
            out.append(amount)
    return out


def normalize_verify_result(data: dict) -> dict:
    result = normalize_extract(data)  # 합계금액 → 결제금액, 거래일자 → 사용일자 (별칭 표)
    result["품목금액"] = parse_item_amounts(_find_items(data)) if isinstance(data, dict) else []
    return result


def run_verify_agent(file_id: str, file_name: str) -> tuple[dict, str]:
    """반환: (정규화된 검증 결과, 원본 output_text)"""
    if config.USE_MOCK:
        data, raw = run_agent_mock(config.VERIFY_AGENT_ID, file_name)
    else:
        data, raw = run_agent(config.VERIFY_AGENT_ID, file_id, config.VERIFY_CONFIG_ID)
    return normalize_verify_result(data), raw
