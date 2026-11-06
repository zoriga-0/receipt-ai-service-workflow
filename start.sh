#!/bin/bash
# 영수증 콜렉터 한 번에 켜기 (Mac mini)
#   1) 홈 화면 아이콘 설정 (pwa.py)
#   2) FastAPI 분석 서버  → 127.0.0.1:8000  (Mac 안에서만 열림)
#   3) Streamlit 화면     → 127.0.0.1:8501  (Tailscale Funnel로 인터넷에 연다)
#
# 사용법: venv를 켠 터미널에서   ./start.sh
# 끄기:   Ctrl + C  (화면과 서버가 같이 꺼진다)
set -e
cd "$(dirname "$0")"

export API_URL="http://127.0.0.1:8000"
# 화면 ↔ 서버 내부 키: 켤 때마다 새로 만든다
export API_TOKEN="${API_TOKEN:-$(python -c 'import secrets; print(secrets.token_hex(16))')}"

python pwa.py

# --reload: 분석 코드(.py)를 고치면 서버가 알아서 다시 읽는다 (다시 켤 필요 없음)
uvicorn server:app --host 127.0.0.1 --port 8000 --reload &
SERVER_PID=$!
trap 'kill $SERVER_PID 2>/dev/null' EXIT INT TERM

streamlit run streamlit_app.py \
  --server.address 127.0.0.1 \
  --server.port 8501 \
  --server.headless true
