from receipt_extract_agent import run_receipt_extract_agent
from expense_review_agent import run_expense_review_agent


def run_receipt_workflow(uploaded_files):
    extract_results = run_receipt_extract_agent(uploaded_files)
    review_results = run_expense_review_agent(uploaded_files)

    review_map = {item["file_name"]: item for item in review_results}

    merged_results = []
    for row in extract_results:
        file_name = row["file_name"]
        review = review_map.get(file_name, {})

        merged_results.append({
            "사용일자": row["사용일자"],
            "상호명": row["상호명"],
            "결제금액": row["결제금액"],
            "경비구분": row["경비구분"],
            "통화": row["통화"],
            "검토여부": review.get("검토여부", ""),
            "사유": review.get("사유", "")
        })

    return merged_results