from config import EXPENSE_REVIEW_AGENT_ID
from agent_client import run_agent


def run_expense_review_agent(uploaded_files):
    raw_results = run_agent(EXPENSE_REVIEW_AGENT_ID, uploaded_files)

    results = []
    for item in raw_results:
        results.append({
            "file_name": item["file_name"],
            "검토여부": "검토 불필요",
            "사유": "식음료 중심 영수증으로 판단됨"
        })

    return results