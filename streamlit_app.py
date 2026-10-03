import streamlit as st
from service import process_receipts

st.set_page_config(page_title="영수증 경비 정리 서비스", layout="wide")

st.title("영수증 경비 정리 서비스")
st.write("영수증 파일을 업로드하고, 결과를 표와 엑셀로 확인하는 MVP입니다.")

uploaded_files = st.file_uploader(
    "영수증 이미지 또는 PDF를 업로드하세요.",
    type=["png", "jpg", "jpeg", "pdf"],
    accept_multiple_files=True
)

if st.button("분석 시작"):
    if not uploaded_files:
        st.warning("먼저 영수증 파일을 업로드해주세요.")
    else:
        df, excel_bytes = process_receipts(uploaded_files)

        st.subheader("분석 결과")
        st.dataframe(df, use_container_width=True)

        st.download_button(
            label="엑셀 다운로드",
            data=excel_bytes,
            file_name="expense_result.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )