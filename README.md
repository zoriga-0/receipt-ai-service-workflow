# 영수증 콜렉터 (Receipt AI Service Workflow)

영수증 사진을 여러 장 올리면 1장당 1행으로 정리하고 엑셀·CSV로 내려받는 서비스입니다.
Upstage Studio 워크플로우 3개(1번 읽기, 2번 분류, 3번 검증)와 Solar(목적 반영 분류)를 씁니다.

## 구성

```
브라우저 ──https──▶ Tailscale Funnel ──▶ Streamlit 화면 (127.0.0.1:8501)
                                              │  영수증 한 장씩
                                              ▼
                                         FastAPI 서버 (127.0.0.1:8000) ──▶ Upstage
```

- 화면(`streamlit_app.py`)은 결과 표·검토·내보내기만 맡고, 분석은 서버(`server.py`)가 한다.
- `API_URL`을 비워두면 화면이 직접 분석한다 (서버 없이도 동작).

## 처음 한 번

```bash
pip install -r requirements.txt
```

`.env` 파일에 최소한 아래를 넣는다.

```
UPSTAGE_API_KEY=...
APP_PASSWORD=접속비밀번호      # 비워두면 비밀번호 없이 열림
```

## 켜기 (Mac mini)

```bash
source venv/bin/activate
./start.sh                   # 서버 + 화면을 같이 켠다. 끄기는 Ctrl + C
```

인터넷에 열기 (다른 터미널에서 한 번):

```bash
tailscale funnel --bg 8501   # https://<맥이름>.<테일넷>.ts.net 으로 열림
tailscale funnel --bg off    # 닫기
```

## 서버만 시험하기

```bash
uvicorn server:app --host 127.0.0.1 --port 8000
```

브라우저에서 http://127.0.0.1:8000/docs 를 열면 영수증을 올려 결과 JSON을 볼 수 있다.

| 주소 | 하는 일 |
| --- | --- |
| `GET /health` | 서버 상태와 비어 있는 설정 확인 |
| `POST /receipts/analyze` | 영수증 한 장(`file`) + 목적(`purpose`) + 경비 구분 목록(`categories`) → 결과 행과 상세 |
