"""롯데시네마 PC웹 반자동 예매 (개인용·일회성).

흐름: [자동 로그인] → [상영시간표 API로 회차 오픈 감시] → [예매 화면 진입·회차 클릭]
      → [선호 좌석 블록 자동 선택] → [결제창 도착 시 알림 후 멈춤]. 결제는 직접.

- 아이디/비밀번호는 환경변수 LOTTE_ID / LOTTE_PW 로만 받습니다(파일에 저장 금지).
- 캡차·본인인증이 뜨면 자동 진행을 멈추고 알림 → 사람이 처리하면 이어서 진행.
- 회차 감시는 페이지 새로고침 대신 공개 상영시간표 API(GetPlaySequence)를 씁니다.

사용법:
  export LOTTE_ID=... LOTTE_PW=...
  python lotte_booker.py --config lotte.yaml            # 실제 실행
  python lotte_booker.py --config lotte.yaml --dry-seats # 좌석 우선순위만 출력
"""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

import yaml
from playwright.sync_api import Page, TimeoutError as PWTimeout, sync_playwright

from movie_booker import notify, run_step, target

API_URL = "https://www.lottecinema.co.kr/LCWS/Ticketing/TicketingData.aspx"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)


# ───────────────────── 좌석 우선순위 계산 ─────────────────────

def seat_blocks(rows: str, cols: range, count: int, prefer_row: str, prefer_cols: list[int]):
    """구역 안에서 count명이 붙어 앉을 수 있는 블록을 선호도 순으로 생성.

    점수 = (선호 행과의 거리, 선호 열 중심과의 거리, 선호 열 밖으로 벗어난 좌석 수)
    → E6-8이 최우선, 그다음 E열 다른 위치, 그다음 D/F열 순.
    """
    center = sum(prefer_cols) / len(prefer_cols)
    pref = set(prefer_cols)
    blocks = []
    for r in rows:
        for start in range(cols.start, cols.stop - count + 1):
            block = list(range(start, start + count))
            mid = sum(block) / count
            score = (
                abs(ord(r) - ord(prefer_row)),
                sum(c not in pref for c in block),
                abs(mid - center),
            )
            blocks.append((score, [f"{r}{c}" for c in block]))
    blocks.sort(key=lambda x: x[0])
    return [b for _, b in blocks]


def seat_singles(rows: str, cols: range, prefer_row: str, prefer_cols: list[int]):
    center = sum(prefer_cols) / len(prefer_cols)
    seats = [(abs(ord(r) - ord(prefer_row)), abs(c - center), f"{r}{c}") for r in rows for c in cols]
    return [s for *_, s in sorted(seats)]


# ───────────────────── 회차 오픈 감시 (API) ─────────────────────

def api_call(api_url: str = API_URL, **params) -> dict:
    p = {"channelType": "HO", "osType": "W", "osVersion": UA, **params}
    data = urllib.parse.urlencode({"paramList": json.dumps(p)}).encode()
    req = urllib.request.Request(api_url, data=data, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


def find_showing(cfg: dict) -> dict | None:
    w = cfg["watch"]
    res = api_call(
        w.get("api_url", API_URL),
        MethodName="GetPlaySequence",
        playDate=w["date"],
        cinemaID=w["cinema_id"],
        representationMovieCode="",
    )
    items = (res.get("PlaySeqs") or {}).get("Items") or []
    norm = lambda s: (s or "").replace(" ", "").replace(":", "")  # "어벤져스: 둠스데이" ≈ "어벤져스둠스데이"
    hits = []
    for it in items:
        if str(it.get("ScreenID")) != str(w["screen_id"]):
            continue
        if w.get("movie") and norm(w["movie"]) not in norm(it.get("MovieNameKR")):
            continue
        start = it.get("StartTime") or ""
        if w.get("time") and start != w["time"]:
            continue
        if w.get("time_after") and start < w["time_after"]:   # "HH:MM" 문자열 비교로 충분
            continue
        if w.get("min_seats") and int(it.get("BookingSeatCount") or 0) < int(w["min_seats"]):
            continue  # BookingSeatCount = 예매 가능 좌석 수
        hits.append(it)
    return min(hits, key=lambda x: x.get("StartTime") or "") if hits else None  # 조건 내 가장 이른 회차


def watch_open(cfg: dict) -> dict | None:
    w = cfg.get("watch")
    if not w:
        return None
    interval = max(float(w.get("interval_sec", 60)), 20)
    tries = 0
    while True:
        tries += 1
        try:
            hit = find_showing(cfg)
        except Exception as e:
            print(f"[{time.strftime('%H:%M:%S')}] API 오류: {e} — 재시도")
            hit = None
        if hit:
            notify(
                f"회차 오픈! {hit.get('MovieNameKR')} {hit.get('StartTime')} "
                f"{hit.get('ScreenNameKR', '')} 잔여 {hit.get('BookingSeatCount')}석"
            )
            return hit
        print(f"[{time.strftime('%H:%M:%S')}] 미오픈 (시도 {tries}) — {interval:.0f}초 후 재확인")
        time.sleep(interval)


# ───────────────────── 로그인 ─────────────────────

def ensure_login(page: Page, cfg: dict) -> None:
    lg = cfg["login"]
    page.goto(cfg["home_url"], wait_until="domcontentloaded")
    if page.query_selector(lg["logged_in_selector"]):
        print("이미 로그인 상태")
        return
    uid, pw = os.environ.get("LOTTE_ID"), os.environ.get("LOTTE_PW")
    page.goto(lg["url"], wait_until="domcontentloaded")
    if uid and pw:
        try:
            page.fill(lg["id_selector"], uid, timeout=10_000)
            page.fill(lg["pw_selector"], pw, timeout=10_000)
            page.click(lg["submit_selector"], timeout=10_000)
            page.wait_for_selector(lg["logged_in_selector"], timeout=15_000)
            print("자동 로그인 성공")
            return
        except PWTimeout:
            pass
    notify("자동 로그인 실패(또는 계정정보 없음/캡차) — 브라우저에서 직접 로그인해 주세요")
    page.wait_for_selector(lg["logged_in_selector"], timeout=0)  # 사람이 로그인할 때까지 대기
    print("로그인 확인")


# ───────────────────── 좌석 선택 ─────────────────────

def pick_seats(page: Page, cfg: dict) -> list[str]:
    s = cfg["seats"]
    ctx = target(page, s)
    ctx.wait_for_selector(s["map_selector"], timeout=s.get("timeout", 20_000))
    tmpl, bad = s["seat_selector"], s.get("unavailable_class")

    def available(label: str):
        el = ctx.query_selector(tmpl.format(row=label[0], col=label[1:], label=label))
        if el is None or not el.is_visible() or not el.is_enabled():
            return None
        if bad and any(c in (el.get_attribute("class") or "").split() for c in bad.split()):
            return None
        return el

    rows, cols = s["rows"], range(s["cols"][0], s["cols"][1] + 1)
    n = int(s["count"])
    for block in seat_blocks(rows, cols, n, s["prefer_row"], s["prefer_cols"]):
        els = [available(x) for x in block]
        if all(els):
            for el in els:
                el.click()
            return block
    if s.get("allow_split"):
        chosen = []
        for label in seat_singles(rows, cols, s["prefer_row"], s["prefer_cols"]):
            el = available(label)
            if el:
                el.click()
                chosen.append(label)
                if len(chosen) == n:
                    return chosen
    raise RuntimeError(f"선호 구역({rows} {cols.start}-{cols.stop - 1})에 {n}석 연석 없음 — 직접 골라주세요")


# ───────────────────── 메인 ─────────────────────

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="lotte.yaml")
    ap.add_argument("--headless", action="store_true", help="테스트용")
    ap.add_argument("--chromium", default=os.environ.get("CHROMIUM_PATH"))
    ap.add_argument("--dry-seats", action="store_true", help="좌석 우선순위만 출력하고 종료")
    args = ap.parse_args()
    cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))

    s = cfg["seats"]
    if args.dry_seats:
        cols = range(s["cols"][0], s["cols"][1] + 1)
        for i, b in enumerate(seat_blocks(s["rows"], cols, int(s["count"]), s["prefer_row"], s["prefer_cols"]), 1):
            print(f"{i:2d}. {' '.join(b)}")
        return

    state = cfg.get("storage_state", "auth.json")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=args.headless, executable_path=args.chromium,
                                    slow_mo=cfg.get("slow_mo_ms", 0))
        ctx = browser.new_context(storage_state=state if Path(state).exists() else None,
                                  viewport={"width": 1400, "height": 900})
        page = ctx.new_page()
        try:
            ensure_login(page, cfg)
            ctx.storage_state(path=state)
            hit = watch_open(cfg) or {}           # 오픈 전이면 여기서 대기
            fields = {"time": hit.get("StartTime", cfg.get("watch", {}).get("time", "")),
                      "movie": hit.get("MovieNameKR", ""), "screen": hit.get("ScreenNameKR", "")}
            page.goto(cfg["ticketing_url"], wait_until="domcontentloaded")
            for step in cfg.get("steps", []):     # 영화·회차·인원 클릭 ({time} 등은 감지된 회차로 치환)
                step = {k: v.format(**fields) if isinstance(v, str) else v for k, v in step.items()}
                run_step(page, step)
            seats = pick_seats(page, cfg)
            print(f"좌석 선택: {' '.join(seats)}")
            for step in cfg.get("after_seat_steps", []):  # '결제하기' 등
                run_step(page, step)
            if cfg.get("payment_ready_selector"):
                page.wait_for_selector(cfg["payment_ready_selector"], timeout=20_000)
            notify(f"결제창 도착! 좌석 {' '.join(seats)} — 지금 직접 결제하세요.")
        except Exception as e:
            notify(f"자동 진행 중단: {e}\n브라우저에서 직접 이어서 진행하세요.")
        if not args.headless:
            input("결제를 마치면 Enter를 눌러 종료... ")
        browser.close()


if __name__ == "__main__":
    main()
