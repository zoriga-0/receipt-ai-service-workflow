import pandas as pd

from app import run_receipt_workflow
from media import file_hash
from normalize import COLUMNS
from records import join_reason


def process_receipts(files: list[tuple[str, bytes]], on_progress=None, context: dict | None = None):
    """
    files: [(파일명, 바이트), ...]  (HEIC는 미리 JPG로 바꿔서 넘긴다)
    반환: (결과 DataFrame, 파일별 상세, 원본 파일 {행ID: (파일명, 바이트)})

    완전히 같은 파일이 여러 번 올라오면 한 번만 분석하고(API 비용 절약)
    나머지는 '동일 파일 중복'으로 표시한다.
    """
    hashes = [file_hash(data) for _, data in files]
    first_of: dict[str, int] = {}
    unique_idx = []
    for i, h in enumerate(hashes):
        if h not in first_of:
            first_of[h] = i
            unique_idx.append(i)

    rows_u, details_u = run_receipt_workflow(
        [files[i] for i in unique_idx], on_progress=on_progress, context=context
    )
    result_of = {hashes[i]: (row, det) for i, row, det in zip(unique_idx, rows_u, details_u)}

    rows, details, originals = [], [], {}
    for i, (name, data) in enumerate(files):
        row, det = result_of[hashes[i]]
        row = dict(row, 파일명=name, _id=f"r{i}")
        first = first_of[hashes[i]]
        if first != i:
            row["검토여부"] = "검토 필요"
            row["사유"] = join_reason(row.get("사유"), f"동일 파일 중복 업로드: {files[first][0]}")
            det = dict(det, 파일명=name)
        rows.append(row)
        details.append(det)
        originals[row["_id"]] = (name, data)

    df = pd.DataFrame(rows, columns=COLUMNS + ["_id"])
    df["결제금액"] = pd.to_numeric(df["결제금액"], errors="coerce")
    return df, details, originals