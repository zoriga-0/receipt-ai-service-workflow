"""
server.py

영수증 분석 API 서버 (FastAPI)
화면(Streamlit)은 이 서버에 영수증을 한 장씩 보내고, 결과(JSON)만 받는다.
Upstage 키는 이 서버에만 있으면 된다.

실행 (Mac 안에서만 열기):
    uvicorn server:app --host 127.0.0.1 --port 8000
문서·시험 화면:
    http://127.0.0.1:8000/docs
"""

import hmac
import time

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile

import config
from app import process_one
from media import prepare_upload
from normalize import CATEGORIES, parse_categories

app = FastAPI(
    title="영수증 콜렉터 API",
    version="1.0",
    description="영수증 한 장을 받아 1번(읽기)·2번(분류)·3번(검증) 워크플로우와 목적 반영 분류 결과를 돌려준다.",
)


##################################################
# 핵심 처리 (FastAPI 없이도 시험할 수 있게 분리)
##################################################

def analyze_bytes(file_name: str, data: bytes, purpose: str = "", categories: str = "") -> dict:
    """영수증 한 장 분석. 반환: {"file_name", "row", "detail", "elapsed"}"""
    if len(data) > config.MAX_UPLOAD_MB * 1024 * 1024:
        raise ValueError(f"파일이 너무 큽니다 (최대 {config.MAX_UPLOAD_MB}MB).")
    name, data, err = prepare_upload(file_name or "receipt", data)  # 아이폰 HEIC → JPG
    if err:
        raise ValueError(err)
    context = {
        "purpose": (purpose or "").strip(),
        "categories": parse_categories(categories) if (categories or "").strip() else list(CATEGORIES),
    }
    start = time.monotonic()
    row, detail = process_one(name, data, context)
    return {
        "file_name": name,
        "row": row,
        "detail": detail,
        "elapsed": round(time.monotonic() - start, 2),
    }


def check_token(token: str | None) -> None:
    """API_TOKEN을 정했으면, 같은 키를 보낸 요청만 받는다."""
    if config.API_TOKEN and not hmac.compare_digest(token or "", config.API_TOKEN):
        raise HTTPException(status_code=401, detail="내부 키(X-API-Token)가 맞지 않습니다.")


##################################################
# 주소
##################################################

@app.get("/health")
def health():
    """서버가 살아 있는지, 설정이 비어 있지 않은지 확인."""
    missing = config.missing_settings(for_server=True)
    return {"ok": not missing, "mock": config.USE_MOCK, "missing": missing}


@app.post("/receipts/analyze")
def analyze(
    file: UploadFile = File(..., description="영수증 사진 또는 PDF 한 장"),
    purpose: str = Form("", description="지출 목적 (선택). 예: 11월 MT 장보기"),
    categories: str = Form("", description="경비 구분 목록, 쉼표로 구분 (선택)"),
    x_api_token: str | None = Header(None),
):
    check_token(x_api_token)
    missing = config.missing_settings(for_server=True)
    if missing:
        raise HTTPException(status_code=503, detail="서버 설정이 비어 있습니다: " + ", ".join(missing))
    try:
        return analyze_bytes(file.filename, file.file.read(), purpose, categories)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
