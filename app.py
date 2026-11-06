"""
app.py

처리 순서 제어 및 결과 병합.

영수증 1장마다:
  1) 파일 업로드 (1번 업로드한 file_id를 두 Agent가 같이 쓴다)
  2) 1번 Agent(읽기)와 3번 Agent(검증)가 같은 사진을 동시에 읽는다
  3) 2번 Agent(분류)는 사진 대신 1번이 읽은 결과(글)를 받아 분류한다
  4) 업로드 파일 정리 (삭제 확인)
  5) 결과를 1행으로 병합 + 검산 + 1번·3번 비교
여러 장은 MAX_WORKERS 만큼 동시에 처리하고, 업로드 순서대로 돌려준다.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed

import config
from agent_client import AgentError, delete_file, upload_file
from expense_review_agent import run_expense_review_agent, run_expense_review_agent_text
from normalize import merge_row
from receipt_extract_agent import run_receipt_extract_agent
from verify_agent import run_verify_agent, verify_enabled


def _review(file_id: str, file_name: str, detail: dict) -> tuple[dict, str]:
    """
    2번 분류. 1번이 읽은 결과가 있으면 그 글로 분류하고(빠름),
    없거나 실패하면 예전처럼 사진을 직접 읽어 분류한다.
    """
    if config.REVIEW_INPUT == "text" and detail["extract_raw"]:
        try:
            return run_expense_review_agent_text(detail["extract_raw"], file_name)
        except AgentError as e:
            detail["notes"].append(f"글로 분류 실패 → 사진으로 다시 분류: {e}")
    return run_expense_review_agent(file_id, file_name)


def _process_one(file_name: str, data: bytes) -> tuple[dict, dict]:
    detail = {"파일명": file_name, "extract_raw": "", "review_raw": "", "verify_raw": "",
              "errors": [], "notes": []}
    extract = review = verify = None
    file_id = ""

    try:
        if not config.USE_MOCK:
            file_id = upload_file(file_name, data)


        # 읽기(1번)와 검증(3번)은 서로 기다릴 필요가 없어서 동시에 시작한다.
        # 2번이 사진으로 분류하는 모드(file)라면 2번도 1번을 기다릴 필요가 없으니 같이 시작한다.
        review_by_file = config.REVIEW_INPUT != "text"
        with ThreadPoolExecutor(max_workers=3) as pool:
            f_extract = pool.submit(run_receipt_extract_agent, file_id, file_name)
            f_verify = pool.submit(run_verify_agent, file_id, file_name) if verify_enabled() else None
            f_review = pool.submit(run_expense_review_agent, file_id, file_name) if review_by_file else None

            try:
                extract, detail["extract_raw"] = f_extract.result()
            except AgentError as e:
                detail["errors"].append(f"추출 실패: {e}")

            # text 모드: 분류(2번)는 1번 결과를 받아서 한다. 그동안 3번은 계속 돌고 있다.
            try:
                if f_review is not None:
                    review, detail["review_raw"] = f_review.result()
                else:
                    review, detail["review_raw"] = _review(file_id, file_name, detail)
            except AgentError as e:
                detail["errors"].append(f"검토 실패: {e}")

            # 3번 검증은 보조 장치라서, 실패해도 행 전체를 '검토 필요'로 만들지 않고 메모만 남긴다.
            if f_verify is not None:
                try:
                    verify, detail["verify_raw"] = f_verify.result()
                except AgentError as e:
                    detail["notes"].append(f"교차검증 건너뜀: {e}")

    except AgentError as e:
        detail["errors"].append(f"업로드 실패: {e}")
    except Exception as e:  # noqa: BLE001  예상 못한 오류도 행 단위로 기록
        detail["errors"].append(f"처리 오류: {type(e).__name__}: {e}")
    finally:
        if file_id and not delete_file(file_id):
            detail["notes"].append(f"Upstage 파일 삭제를 확인하지 못함 (file_id={file_id})")

    row = merge_row(file_name, extract, review, detail["errors"], verify)
    return row, detail


def run_receipt_workflow(files: list[tuple[str, bytes]], on_progress=None):
    """
    files: [(파일명, 바이트), ...]
    on_progress: 완료될 때마다 호출되는 콜백 (완료 수, 전체 수, 파일명)
    반환: (행 목록, 파일별 상세)
    """
    total = len(files)
    results = [None] * total
    done = 0

    with ThreadPoolExecutor(max_workers=max(1, config.MAX_WORKERS)) as pool:
        futures = {
            pool.submit(_process_one, name, data): i for i, (name, data) in enumerate(files)
        }
        for future in as_completed(futures):
            i = futures[future]
            results[i] = future.result()
            done += 1
            if on_progress:
                on_progress(done, total, files[i][0], results[i][0])

    rows = [r for r, _ in results]
    details = [d for _, d in results]
    return rows, details