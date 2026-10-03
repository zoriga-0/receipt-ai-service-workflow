from config import RECEIPT_EXTRACT_AGENT_ID
from agent_client import run_agent


def run_receipt_extract_agent(uploaded_files):
    raw_results = run_agent(RECEIPT_EXTRACT_AGENT_ID, uploaded_files)

    results = []
    for item in raw_results:
        results.append({
            "file_name": item["file_name"],
            "사용일자": "2022-02-27",
            "상호명": item["file_name"],
            "결제금액": 10300,
            "경비구분": "식비",
            "통화": "KRW"
        })

    return results