# 영화 예매 반자동 스크립트

로그인된 내 계정으로 **회차 오픈 대기 → 회차 클릭 → 인원·좌석 선택 → 결제창**까지 자동 진행하고,
결제창에 도착하면 알림(비프음 + 선택적으로 텔레그램)을 보낸 뒤 멈춥니다. **결제는 직접** 합니다.

- 캡차·대기열·본인인증은 건드리지 않습니다. 막히면 알림을 보내고 브라우저를 열어둡니다.
- 새로고침 간격은 최소 10초로 강제됩니다(차단 방지).
- 개인용·일회성 용도입니다. 재판매 목적 구매는 공연법 위반입니다.

## 1. 설치 (내 PC에서)

```bash
pip install -r requirements.txt
python -m playwright install chromium
```

## 2. 로그인 세션 저장

```bash
cp config.example.yaml config.yaml
python movie_booker.py login --config config.yaml
```
뜬 브라우저에서 직접 로그인하고 터미널에서 Enter → `auth.json` 생성 (절대 공유·커밋 금지).

## 3. 셀렉터 따기 (가장 중요)

극장 사이트마다 버튼 구조가 다르니, 실제 사이트에서 직접 클릭하며 셀렉터를 기록합니다.

```bash
python -m playwright codegen --load-storage=auth.json "예매페이지URL"
```
회차 → 인원 → 좌석 → 결제하기를 직접 눌러보면 오른쪽 창에 `page.click("...")` 코드가 찍힙니다.
그 셀렉터들을 `config.yaml`의 `steps`에 옮기면 됩니다. 좌석 배치도가 iframe 안에 있으면 `frame:`을 지정하세요.

## 4. 실행

```bash
python movie_booker.py run --config config.yaml
```

텔레그램 알림(선택):
```bash
export TELEGRAM_BOT_TOKEN=...   TELEGRAM_CHAT_ID=...
```

## step 종류

| action | 필드 | 설명 |
|---|---|---|
| `click` | `selector` | 클릭 |
| `click_text` | `text`, `exact` | 텍스트로 찾아 클릭 |
| `fill` / `select` | `selector`, `value` | 입력 / 드롭다운 |
| `wait` | `selector` | 나타날 때까지 대기 |
| `sleep` | `seconds` | 고정 대기 |
| `select_seats` | `seats`(우선순위 목록), `count`, `unavailable_class` | 가능한 좌석만 순서대로 선택 |

모든 step에 `frame`, `timeout`(ms) 지정 가능.

## 테스트

`tests/mock/`에 모의 예매 사이트가 있습니다.
```bash
(cd tests/mock && python -m http.server 8765 &)
python movie_booker.py run --config tests/mock_config.yaml --headless
```
