"""
config.py

환경설정: API 키, Studio Agent ID, Config ID, 호출 옵션.
값은 .env(로컬) 또는 Railway Variables(배포)에서 읽는다.
"""

import os

from dotenv import load_dotenv

load_dotenv()


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)))
    except ValueError:
        return default

##################################################
# Upstage API
##################################################

UPSTAGE_API_KEY = _env("UPSTAGE_API_KEY")
UPSTAGE_BASE_URL = _env("UPSTAGE_BASE_URL", "https://api.upstage.ai/v2")
# (예전) 3번 워크플로우: 엑셀 정리·집계. 집계는 Python(excel_builder.py)이 담당한다.
EXCEL_SUMMARY_AGENT_ID = _env("EXCEL_SUMMARY_AGENT_ID", "agt_iBcXUvFaeUGnnEEDJEhJib")

# 3번 워크플로우: 교차 검증. 사진을 한 번 더 읽어 1번 결과(금액·날짜)와 비교한다.
# 따로 지정하지 않으면 기존 3번 Agent를 검증용으로 고쳐 쓴다고 보고 그 ID를 쓴다.
# 끄고 싶으면 VERIFY_AGENT_ID=off 로 둔다.
_verify = _env("VERIFY_AGENT_ID", EXCEL_SUMMARY_AGENT_ID)
VERIFY_AGENT_ID = "" if _verify.lower() in ("off", "0", "none") else _verify


##################################################
# Studio Agent ID ("API로 이용하기"에서 복사한 agt_ 값)
##################################################

RECEIPT_EXTRACT_AGENT_ID = _env("RECEIPT_EXTRACT_AGENT_ID", "agt_5iE2WDDBSUgSQtUKVYTDPB")
EXPENSE_REVIEW_AGENT_ID = _env("EXPENSE_REVIEW_AGENT_ID", "agt_XnU6HKXmfTtzZDXDUdWte7")

# 3번 워크플로우(엑셀 정리·집계): 현재 앱에서는 호출하지 않는다.
# 여러 영수증을 합치는 집계는 Python(excel_builder.py)이 담당한다.
EXCEL_SUMMARY_AGENT_ID = _env("EXCEL_SUMMARY_AGENT_ID", "agt_iBcXUvFaeUGnnEEDJEhJib")

##################################################
# Config ID (선택)
# 비워두면 Studio에 배포된 기본 설정으로 실행된다.
# 특정 설정 버전을 고정하고 싶을 때만 cfg_ 값을 넣는다.
##################################################

RECEIPT_EXTRACT_CONFIG_ID = _env("RECEIPT_EXTRACT_CONFIG_ID")
EXPENSE_REVIEW_CONFIG_ID = _env("EXPENSE_REVIEW_CONFIG_ID")
VERIFY_CONFIG_ID = _env("VERIFY_CONFIG_ID")

##################################################
# 실행 옵션
##################################################

# 1 이면 API를 호출하지 않고 가짜 결과로 화면만 테스트한다.
USE_MOCK = _env("USE_MOCK", "0").lower() in ("1", "true", "yes")

POLL_INTERVAL_SEC = _env_int("POLL_INTERVAL_SEC", 2)
JOB_TIMEOUT_SEC = _env_int("JOB_TIMEOUT_SEC", 180)
MAX_WORKERS = _env_int("MAX_WORKERS", 3)  # 동시에 처리할 영수증 수

# 2번 분류가 무엇을 보고 판단할지: file = 사진을 읽음(기본), text = 1번 추출 결과(글)
# Studio 워크플로우는 파일로만 시작할 수 있어서 기본값은 file.
REVIEW_INPUT = _env("REVIEW_INPUT", "file").lower()

# 목적 반영 분류: Upstage Solar 모델을 직접 부른다 (Studio 바깥, 같은 API 키)
# solar-mini4 = 빠름, solar-pro4 = 더 정확함
SOLAR_BASE_URL = _env("SOLAR_BASE_URL", "https://api.upstage.ai/v1")
PURPOSE_MODEL = _env("PURPOSE_MODEL", "solar-mini4")

##################################################
# 내 Mac에서 서버 + 화면으로 나눠 돌릴 때
##################################################

# 화면이 부를 FastAPI 서버 주소. 비워두면 화면이 직접 처리한다 (예전 방식).
API_URL = _env("API_URL").rstrip("/")
# 화면 ↔ 서버 사이 내부 키 (start.sh가 켤 때마다 새로 만든다)
API_TOKEN = _env("API_TOKEN")
# 화면 접속 비밀번호. 비워두면 비밀번호 없이 열린다.
APP_PASSWORD = _env("APP_PASSWORD")
# 서버가 받는 파일 크기 한도
MAX_UPLOAD_MB = _env_int("MAX_UPLOAD_MB", 20)


def missing_settings(for_server: bool = False) -> list[str]:
    """
    실제 API 호출에 필요한데 비어 있는 설정 이름 목록.
    화면이 서버(API_URL)를 쓰면 Upstage 키는 서버에만 있으면 되므로 화면 쪽은 확인하지 않는다.
    """
    if USE_MOCK or (API_URL and not for_server):
        return []
    missing = []
    if not UPSTAGE_API_KEY:
        missing.append("UPSTAGE_API_KEY")
    if not RECEIPT_EXTRACT_AGENT_ID:
        missing.append("RECEIPT_EXTRACT_AGENT_ID")
    if not EXPENSE_REVIEW_AGENT_ID:
        missing.append("EXPENSE_REVIEW_AGENT_ID")
    return missing