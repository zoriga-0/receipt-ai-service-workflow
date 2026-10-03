import pandas as pd
from app import run_receipt_workflow
from excel_builder import dataframe_to_excel_bytes


def process_receipts(uploaded_files):
    result_rows = run_receipt_workflow(uploaded_files)
    df = pd.DataFrame(result_rows)
    excel_bytes = dataframe_to_excel_bytes(df)

    return df, excel_bytes