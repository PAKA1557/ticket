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

---

# 롯데시네마 전용: `lotte_booker.py`

부산본점 5관 · 어벤져스: 둠스데이 · 2026-12-16 12:00 이후 기준으로 설정된 예시: `lotte.example.yaml`

1. **자동 로그인**: 환경변수 `LOTTE_ID`, `LOTTE_PW`로 로그인(파일에 저장 안 함). 캡차 등으로 실패하면 알림 후 직접 로그인할 때까지 대기.
2. **오픈 감시**: 공개 상영시간표 API(`GetPlaySequence`)로 1분마다 확인 → 5관·영화명·12:00 이후·잔여석 ≥ 인원 조건의 **가장 이른 회차**를 찾으면 진행.
3. **예매 화면**: 지역 → 지점 → 영화 → 날짜 → 감지된 회차 시간(`{time}` 자동 치환) → 인원.
4. **좌석**: D–F열 5–9번 안에서 연석 블록을 선호도순으로 시도 (`--dry-seats`로 순서 확인)
   `E6-8 → E5-7 → E7-9 → D6-8 → F6-8 → …`
5. **결제창 도착 → 알림 후 멈춤.** 결제는 직접.

```bash
cp lotte.example.yaml lotte.yaml
python -m playwright codegen https://www.lottecinema.co.kr/NLCHS/   # TODO 셀렉터 확인
export LOTTE_ID=내아이디 LOTTE_PW=내비번
python lotte_booker.py --config lotte.yaml
```

> `lotte.example.yaml`의 `TODO` 셀렉터(로그인 폼, 인원 버튼, 좌석 요소, 매진 클래스, 결제창 표시)는
> 실제 사이트에서 검증되지 않았습니다. codegen으로 확인해 채워야 합니다.

모의 서버 테스트: `(python tests/lotte_mock/server.py &)` 후
`LOTTE_ID=t LOTTE_PW=t python lotte_booker.py --config tests/lotte_mock_config.yaml --headless`
