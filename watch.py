"""롯데시네마 예매 오픈 감시 (알림 전용, 표준 라이브러리만 사용).

공개 상영시간표 조회(GetPlaySequence)를 주기적으로 확인해서, 조건에 맞는 회차가
처음 나타나면 PC(화면 알림+소리)와 폰(ntfy 앱 / 텔레그램)으로 알립니다. 예매는 직접 합니다.

기본값: 부산본점 · 5관 · 어벤져스: 둠스데이 · 2026-12-16 · 12:00 이후 · 잔여 3석 이상

  python watch.py --list --date 2026-11-24     # 먼저 오늘/내일 날짜로 실제 조회되는지 확인
  python watch.py                              # 감시 시작
  python watch.py --once                       # 한 번만 확인하고 종료

  python watch.py --test-notify                # PC·폰 알림 시험

폰 알림: NTFY_TOPIC (권장) 또는 TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID 환경변수
"""

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request

API_URL = "https://www.lottecinema.co.kr/LCWS/Ticketing/TicketingData.aspx"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)
# 공개 자료마다 지점코드 표기가 달라서 순서대로 시도하고, 응답이 오는 형식을 기억함
CINEMA_ID_FORMATS = ["1|0101|{id}", "1|101|{id}", "1|1|{id}"]
MIN_INTERVAL = 20


def log(msg: str) -> None:
    print(f"[{time.strftime('%m-%d %H:%M:%S')}] {msg}", flush=True)


# ───────────────────────── 알림 ─────────────────────────
# PC: OS 기본 알림 + 소리 / 폰: ntfy 앱(권장, 가입 불필요) 또는 텔레그램
# 한 채널이 실패해도 나머지는 계속 보냄.

def _run(cmd):
    import subprocess
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)


def _ps_quote(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def desktop_notify(title: str, body: str) -> None:
    """PC 화면 알림 + 소리. 외부 패키지 없이 OS 기본 기능만 사용."""
    import platform
    import threading
    system = platform.system()
    if system == "Windows":
        # 토스트 알림(우측 하단) — Windows PowerShell 기본 API
        ps = (
            "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType=WindowsRuntime] > $null;"
            "$t=[Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02);"
            "$x=$t.GetElementsByTagName('text');"
            f"$x.Item(0).AppendChild($t.CreateTextNode({_ps_quote(title)})) > $null;"
            f"$x.Item(1).AppendChild($t.CreateTextNode({_ps_quote(body)})) > $null;"
            "$n=[Windows.UI.Notifications.ToastNotification]::new($t);"
            "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("
            "'{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\\WindowsPowerShell\\v1.0\\powershell.exe').Show($n)"
        )
        try:
            _run(["powershell", "-NoProfile", "-Command", ps])
        except Exception as e:
            log(f"윈도우 알림 실패: {e}")
        try:
            import winsound
            for _ in range(5):
                winsound.Beep(1200, 300)
                time.sleep(0.15)
        except Exception:
            pass
        # 토스트를 놓쳐도 보이도록 팝업창도 띄움(감시는 멈추지 않게 별도 스레드)
        try:
            import ctypes
            threading.Thread(
                target=lambda: ctypes.windll.user32.MessageBoxW(0, body, title, 0x40 | 0x40000),
                daemon=True,
            ).start()
        except Exception:
            pass
    elif system == "Darwin":
        esc = lambda x: x.replace("\\", "\\\\").replace('"', '\\"')
        try:
            _run(["osascript", "-e",
                  f'display notification "{esc(body)}" with title "{esc(title)}" sound name "Glass"'])
            for _ in range(3):
                _run(["afplay", "/System/Library/Sounds/Glass.aiff"])
        except Exception as e:
            log(f"맥 알림 실패: {e}")
    else:
        try:
            _run(["notify-send", "-u", "critical", title, body])
        except Exception:
            pass


def ntfy_notify(topic: str, title: str, body: str, server: str = "https://ntfy.sh") -> None:
    # JSON 방식: 한글 제목도 깨지지 않음
    payload = {
        "topic": topic, "title": title, "message": body,
        "priority": 5,                     # urgent — 폰에서 강하게 울림
        "tags": ["movie_camera"],
        "click": "https://www.lottecinema.co.kr/NLCHS/Ticketing",
    }
    req = urllib.request.Request(
        server.rstrip("/"), data=json.dumps(payload).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json", "User-Agent": "movie-open-watcher"},
    )
    with urllib.request.urlopen(req, timeout=10):
        pass


def telegram_notify(token: str, chat: str, text: str) -> None:
    data = urllib.parse.urlencode({"chat_id": chat, "text": text}).encode()
    with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage", data=data, timeout=10):
        pass


def notify(msg: str, title: str = "롯데시네마 예매 오픈!") -> None:
    print(f"\a\n{'=' * 50}\n{title}\n{msg}\n{'=' * 50}", flush=True)
    sent = ["터미널"]

    desktop_notify(title, msg)
    sent.append("PC")

    topic = os.environ.get("NTFY_TOPIC")
    if topic:
        try:
            ntfy_notify(topic, title, msg, os.environ.get("NTFY_SERVER", "https://ntfy.sh"))
            sent.append("폰(ntfy)")
        except Exception as e:
            log(f"ntfy 전송 실패: {e}")

    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if token and chat:
        try:
            telegram_notify(token, chat, f"{title}\n{msg}")
            sent.append("텔레그램")
        except Exception as e:
            log(f"텔레그램 전송 실패: {e}")

    if len(sent) == 2:
        log("폰 알림 미설정 — NTFY_TOPIC 환경변수를 설정하면 폰으로도 받습니다 (README 참고)")
    log("알림 전송: " + ", ".join(sent))


def fetch(api_url, date, cinema_id):
    params = {
        "MethodName": "GetPlaySequence", "channelType": "HO", "osType": "W", "osVersion": UA,
        "playDate": date, "cinemaID": cinema_id, "representationMovieCode": "",
    }
    data = urllib.parse.urlencode({"paramList": json.dumps(params)}).encode()
    req = urllib.request.Request(api_url, data=data, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=15) as r:
        res = json.loads(r.read().decode("utf-8"))
    return (res.get("PlaySeqs") or {}).get("Items") or []


class Watcher:
    def __init__(self, a: argparse.Namespace):
        self.a = a
        self.cinema_id = a.cinema_id_raw  # 직접 지정했으면 그대로 사용

    def items(self):
        if self.cinema_id:
            return fetch(self.a.api_url, self.a.date, self.cinema_id)
        # 지점코드 형식 자동 탐색: 결과가 나오는 첫 형식을 고정
        for fmt in CINEMA_ID_FORMATS:
            cid = fmt.format(id=self.a.cinema)
            got = fetch(self.a.api_url, self.a.date, cid)
            if got:
                self.cinema_id = cid
                log(f"지점코드 형식 확정: {cid}")
                return got
        return []

    def match(self, it: dict) -> bool:
        a = self.a
        norm = lambda s: (s or "").replace(" ", "").replace(":", "")
        if a.screen and a.screen not in (it.get("ScreenNameKR") or "") and str(it.get("ScreenID")) != a.screen:
            return False
        if a.movie and norm(a.movie) not in norm(it.get("MovieNameKR")):
            return False
        if a.after and (it.get("StartTime") or "") < a.after:
            return False
        # BookingSeatCount = 예매 '가능' 좌석 수
        if a.min_seats and int(it.get("BookingSeatCount") or 0) < a.min_seats:
            return False
        return True


def describe(it: dict) -> str:
    return (f"{it.get('StartTime')}{'~' + it['EndTime'] if it.get('EndTime') else ''} {it.get('ScreenNameKR', '')} "
            f"{it.get('MovieNameKR')} · 잔여 {it.get('BookingSeatCount')}석"
            f"/{it.get('TotalSeatCount', '?')}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--date", default="2026-12-16")
    ap.add_argument("--cinema", default="2004", help="지점 번호 (부산본점=2004)")
    ap.add_argument("--cinema-id-raw", default=None, help="지점코드 전체를 직접 지정 (예: 1|0101|2004)")
    ap.add_argument("--screen", default="5관", help="상영관 이름 일부 또는 ScreenID. 빈 값이면 전체")
    ap.add_argument("--movie", default="어벤져스: 둠스데이", help="영화명 일부 (공백·콜론 무시)")
    ap.add_argument("--after", default="12:00", help="이 시각 이후 시작 회차만 (HH:MM)")
    ap.add_argument("--min-seats", type=int, default=3, help="잔여석이 이보다 적으면 무시")
    ap.add_argument("--interval", type=float, default=60, help=f"확인 간격(초), 최소 {MIN_INTERVAL}")
    ap.add_argument("--once", action="store_true", help="한 번만 확인")
    ap.add_argument("--keep", action="store_true", help="첫 알림 후에도 새 회차가 생길 때마다 계속 알림")
    ap.add_argument("--list", action="store_true", help="조건 무시하고 그 날짜 전체 회차 출력 후 종료")
    ap.add_argument("--test-notify", action="store_true", help="PC·폰 알림이 오는지 시험 발송")
    ap.add_argument("--api-url", default=API_URL, help=argparse.SUPPRESS)  # 테스트용
    a = ap.parse_args()
    a.interval = max(a.interval, MIN_INTERVAL)

    if a.test_notify:
        notify("테스트 알림입니다. 이게 보이면 정상!", title="예매 감시 알림 테스트")
        return 0

    w = Watcher(a)

    if a.list:
        items = w.items()
        if not items:
            print(f"{a.date} 회차 없음 (예매 미오픈이거나 지점코드 형식 문제)")
            return 1
        for it in sorted(items, key=lambda x: (str(x.get("ScreenNameKR")), x.get("StartTime") or "")):
            print(("★ " if w.match(it) else "  ") + describe(it) + f"  [ScreenID {it.get('ScreenID')}]")
        print(f"\n지점코드 {w.cinema_id} · ★ = 현재 조건에 맞는 회차")
        return 0

    log(f"감시 시작: {a.date} 지점 {a.cinema} {a.screen or '전체관'} '{a.movie}' "
        f"{a.after} 이후 잔여 {a.min_seats}석↑ · {a.interval:.0f}초 간격")
    seen = set()
    tries = 0
    while True:
        tries += 1
        try:
            items = w.items()
            hits = sorted((it for it in items if w.match(it)), key=lambda x: x.get("StartTime") or "")
            new = [it for it in hits if f"{it.get('ScreenID')}|{it.get('StartTime')}" not in seen]
            if new:
                seen.update(f"{it.get('ScreenID')}|{it.get('StartTime')}" for it in new)
                notify("\n".join(describe(it) for it in new) + "\n→ 지금 바로 예매하세요")
                if not a.keep:
                    return 0
            else:
                total = f"전체 {len(items)}회차 중 조건 일치 없음" if items else "회차 없음(미오픈)"
                log(f"#{tries} {total}")
        except Exception as e:
            log(f"#{tries} 조회 실패: {e}")
        if a.once:
            return 2
        time.sleep(a.interval)


if __name__ == "__main__":
    sys.exit(main())
