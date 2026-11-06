"""
api_client.py

화면(Streamlit)이 FastAPI 서버(server.py)에 영수증을 보내는 부분.
API_URL을 정했을 때만 쓴다. 정하지 않으면 화면이 직접 처리한다(예전 방식).

영수증은 한 장씩 동시에 보낸다 → 진행 표시("3/9장 완료")가 그대로 살아 있다.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

import config
from normalize import CATEGORIES, merge_row


def _headers() -> dict:
    return {"X-API-Token": config.API_TOKEN} if config.API_TOKEN else {}


def server_status() -> tuple[bool, str]:
    """(서버를 쓸 수 있는지, 안내 문구)"""
    try:
        r = requests.get(f"{config.API_URL}/health", timeout=5)
        r.raise_for_status()
        data = r.json()
    except Exception as e:  # noqa: BLE001
        return False, f"분석 서버에 연결하지 못했어요 ({type(e).__name__})."
    if not data.get("ok"):
        return False, "분석 서버 설정이 비어 있어요: " + ", ".join(data.get("missing") or [])
    return True, ""


def _error_result(name: str, message: str, context: dict | None) -> tuple[dict, dict]:
    detail = {"파일명": name, "extract_raw": "", "review_raw": "", "verify_raw": "",
              "purpose_raw": "", "errors": [message], "notes": []}
    return merge_row(name, None, None, detail["errors"], context=context), detail


def analyze_one(name: str, data: bytes, context: dict | None = None) -> tuple[dict, dict]:
    """영수증 한 장을 서버에 보내고 (행, 상세)를 받는다. 실패해도 예외 대신 '검토 필요' 행을 돌려준다."""
    context = context or {}
    form = {
        "purpose": context.get("purpose", ""),
        "categories": ", ".join(context.get("categories") or CATEGORIES),
    }
    try:
        r = requests.post(
            f"{config.API_URL}/receipts/analyze",
            files={"file": (name, data)},
            data=form,
            headers=_headers(),
            timeout=config.JOB_TIMEOUT_SEC * 2,
        )
    except Exception as e:  # noqa: BLE001
        return _error_result(name, f"분석 서버 연결 실패: {type(e).__name__}", context)
    if r.status_code != 200:
        try:
            msg = r.json().get("detail", "")
        except ValueError:
            msg = r.text[:200]
        return _error_result(name, f"분석 서버 오류({r.status_code}): {msg}", context)
    body = r.json()
    return body["row"], body["detail"]


def run_via_api(files: list[tuple[str, bytes]], on_progress=None, context: dict | None = None):
    """
    app.run_receipt_workflow와 같은 모양: (행 목록, 파일별 상세)를 돌려준다.
    service.process_receipts(..., runner=run_via_api) 로 쓴다.
    """
    total = len(files)
    results = [None] * total
    done = 0
    with ThreadPoolExecutor(max_workers=max(1, config.MAX_WORKERS)) as pool:
        futures = {
            pool.submit(analyze_one, name, data, context): i for i, (name, data) in enumerate(files)
        }
        for future in as_completed(futures):
            i = futures[future]
            results[i] = future.result()
            done += 1
            if on_progress:
                on_progress(done, total, files[i][0], results[i][0])
    return [r for r, _ in results], [d for _, d in results]
