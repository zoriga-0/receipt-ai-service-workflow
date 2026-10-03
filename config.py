import os
from dotenv import load_dotenv

load_dotenv()

UPSTAGE_API_KEY = os.getenv("UPSTAGE_API_KEY", "")

RECEIPT_EXTRACT_AGENT_ID = "agt_5iE2WDDBSUgSQtUKVYTDPB"
EXPENSE_REVIEW_AGENT_ID = "agt_XnU6HKXmfTtzZDXDUdWte7"
EXCEL_SUMMARY_AGENT_ID = "agt_iBcXUvFaeUGnnEEDJEhJib"