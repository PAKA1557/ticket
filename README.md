# 롯데시네마 예매 오픈 감시

롯데시네마 공개 상영시간표를 주기적으로 확인하다가 조건에 맞는 회차가 열리면 알려줍니다.
**알림만 보내고 예매는 직접** 합니다. Python 3.6+ 표준 라이브러리만 사용(설치할 것 없음).

기본 조건: 부산본점 · 5관 · 어벤져스: 둠스데이 · 2026-12-16 · 12:00 이후 · 잔여 3석 이상 · 60초 간격

## 1. 먼저 동작 확인 (꼭!)

지점코드·상영관 이름은 공개 자료 기준 추정이라, 오늘/내일 날짜로 실제 조회되는지 확인하세요.

**실행은 터미널(PowerShell/명령 프롬프트/터미널 앱)에서** 하세요. `>>>`가 보이는 파이썬 창에 붙여넣으면 SyntaxError가 납니다.

```bash
python watch.py --list --date 2026-11-24 --movie ""
```
회차 목록과 `ScreenID`가 나오면 정상입니다. "회차 없음"이면 `--cinema-id-raw "1|0101|2004"` 등으로 바꿔보세요.

## 2. 감시 시작

```bash
python watch.py
```
- 조건에 맞는 회차가 처음 보이면 비프음 + 알림 출력 후 종료 (`--keep`이면 새 회차마다 계속 알림)
- PC 절전 모드를 꺼두세요. 꺼지면 감시도 멈춥니다.

## 알림 설정 (PC + 폰 동시)

- **PC**: 따로 설정할 것 없음. 윈도우는 우측 하단 알림 + 비프음 + 팝업창, 맥은 알림센터 + 소리.
- **폰**: [ntfy](https://ntfy.sh) 앱 사용(무료, 가입 불필요)
  1. 폰에 **ntfy** 앱 설치 (Play 스토어 / App Store)
  2. 앱에서 `+` → 토픽 이름 입력 (남이 못 맞추게 길게, 예: `lotte-doomsday-8f3k2q9x`)
  3. PC에서 같은 토픽 이름을 환경변수로 지정하고 테스트:

Windows (PowerShell):
```powershell
$env:NTFY_TOPIC="lotte-doomsday-8f3k2q9x"; python watch.py --test-notify
```
macOS:
```bash
NTFY_TOPIC=lotte-doomsday-8f3k2q9x python3 watch.py --test-notify
```
PC와 폰 모두 "테스트 알림"이 오면 같은 창에서 `python watch.py`로 감시를 시작하세요.
(PowerShell의 `$env:`는 그 창에서만 유지됩니다.)

> ntfy.sh 토픽은 이름을 아는 사람은 누구나 볼 수 있으니 추측하기 어려운 이름을 쓰세요. 알림 내용은 상영 회차 정보뿐입니다.
> 텔레그램을 선호하면 `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`를 설정해도 됩니다(동시 사용 가능).

## 옵션

| 옵션 | 기본값 | 설명 |
|---|---|---|
| `--date` | 2026-12-16 | 상영일 |
| `--cinema` | 2004 | 지점 번호 (부산본점) |
| `--screen` | 5관 | 상영관 이름 일부 또는 ScreenID, `""`면 전체 |
| `--movie` | 어벤져스: 둠스데이 | 영화명 일부 (공백·콜론 무시) |
| `--after` | 12:00 | 이 시각 이후 시작 회차만 |
| `--min-seats` | 3 | 잔여석 최소 |
| `--interval` | 60 | 확인 간격(초), 최소 20 |
| `--once` / `--keep` / `--list` | | 1회 확인 / 계속 알림 / 전체 회차 출력 |
| `--test-notify` | | PC·폰 알림 시험 발송 |

## 알림 오면 할 일
미리 로그인·결제수단 등록 → 회차 선택 → 좌석 **E6-8 → E5-7 → E7-9 → D/F열 6-8** 순으로 노리기 → 결제.

## 테스트
```bash
(python tests/mock_api.py &) ; python watch.py --api-url http://127.0.0.1:8767/ --interval 20
```
