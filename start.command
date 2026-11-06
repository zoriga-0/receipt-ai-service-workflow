#!/bin/bash
# 영수증 콜렉터 자동 실행 (Mac mini)
#
# 더블클릭하면 터미널이 열리고 서버 + 화면이 켜진다.
# 시스템 설정 → 일반 → 로그인 항목 → '+' 로 이 파일을 넣으면 Mac을 켤 때마다 자동으로 켜진다.
# 혹시 꺼지면 10초 뒤 다시 켠다. 완전히 끄려면 이 터미널 창을 닫는다.
cd "$(dirname "$0")"

# 가상환경(venv) 찾기: 프로젝트 폴더 안이나 바로 위 폴더
for v in venv .venv ../venv ../.venv ../../venv ../../.venv; do
  if [ -f "$v/bin/activate" ]; then
    source "$v/bin/activate"
    echo "가상환경: $(cd "$v" && pwd)"
    break
  fi
done
if ! command -v streamlit >/dev/null 2>&1; then
  echo "streamlit을 찾지 못했어요. 가상환경 위치를 확인해 주세요."
  read -r -p "엔터를 누르면 창이 닫혀요."
  exit 1
fi

while true; do
  bash start.sh
  echo "$(date '+%H:%M:%S') 꺼졌어요. 10초 뒤 다시 켭니다. (그만 쓰려면 창을 닫으세요)"
  sleep 10
done
