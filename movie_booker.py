"""영화 예매 반자동 스크립트 (개인용·일회성).

로그인된 내 계정으로 [상영시간 오픈 대기 → 회차 클릭 → 인원/좌석 선택 → 결제창]까지
자동으로 진행하고, 결제창에 도착하면 알림을 보낸 뒤 멈춥니다. 결제는 직접 합니다.

캡차/대기열/본인인증은 건드리지 않습니다. 단계가 막히면 즉시 알림을 보내고
브라우저를 그대로 열어둬서 사람이 이어서 진행할 수 있게 합니다.

사용법:
  python movie_booker.py login  --config config.yaml   # 1) 직접 로그인 → 세션 저장
  python movie_booker.py run    --config config.yaml   # 2) 자동 진행
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import yaml
from playwright.sync_api import Frame, Page, TimeoutError as PWTimeout, sync_playwright


# ───────────────────────── 알림 ─────────────────────────

def notify(msg: str) -> None:
    print(f"\a[알림] {msg}", flush=True)  # \a = 터미널 비프음
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not (token and chat_id):
        return
    try:
        data = urllib.parse.urlencode({"chat_id": chat_id, "text": msg}).encode()
        urllib.request.urlopen(
            f"https://api.telegram.org/bot{token}/sendMessage", data=data, timeout=10
        )
    except Exception as e:  # 알림 실패가 예매를 막으면 안 됨
        print(f"[경고] 텔레그램 전송 실패: {e}")


# ───────────────────────── 헬퍼 ─────────────────────────

def target(page: Page, step: dict) -> Page | Frame:
    """step에 frame이 지정돼 있으면 해당 iframe 안에서 동작."""
    sel = step.get("frame")
    if not sel:
        return page
    handle = page.wait_for_selector(sel, timeout=step.get("timeout", 10_000))
    frame = handle.content_frame()
    if frame is None:
        raise RuntimeError(f"iframe을 찾을 수 없음: {sel}")
    return frame


def wait_until_open(page: Page, cfg: dict) -> None:
    """오픈 감지 셀렉터가 나타날 때까지 새로고침하며 대기."""
    w = cfg.get("wait_open")
    if not w:
        return
    interval = max(float(w.get("interval_sec", 60)), 10)  # 최소 10초 — 서버 부담·차단 방지
    selector = w["selector"]
    tries = 0
    while True:
        tries += 1
        try:
            target(page, w).wait_for_selector(selector, timeout=5_000, state="visible")
            notify("상영 회차 오픈 감지! 자동 진행 시작")
            return
        except PWTimeout:
            print(f"[{time.strftime('%H:%M:%S')}] 아직 미오픈 (시도 {tries}) — {interval:.0f}초 후 재확인")
            time.sleep(interval)
            page.reload(wait_until="domcontentloaded")


def select_seats(ctx: Page | Frame, step: dict) -> int:
    """우선순위 좌석 목록에서 선택 가능한 좌석을 count개까지 클릭."""
    want = int(step.get("count", 1))
    bad_cls = step.get("unavailable_class")
    picked = 0
    for sel in step["seats"]:
        if picked >= want:
            break
        el = ctx.query_selector(sel)
        if el is None or not el.is_visible() or not el.is_enabled():
            continue
        if bad_cls and bad_cls in (el.get_attribute("class") or "").split():
            continue
        el.click()
        picked += 1
        print(f"  좌석 선택: {sel}")
    return picked


def run_step(page: Page, step: dict) -> None:
    action = step["action"]
    timeout = step.get("timeout", 10_000)
    ctx = target(page, step)
    label = step.get("name", action)
    print(f"▶ {label}")

    if action == "click":
        ctx.click(step["selector"], timeout=timeout)
    elif action == "click_text":
        ctx.get_by_text(step["text"], exact=step.get("exact", False)).first.click(timeout=timeout)
    elif action == "fill":
        ctx.fill(step["selector"], str(step["value"]), timeout=timeout)
    elif action == "select":
        ctx.select_option(step["selector"], str(step["value"]), timeout=timeout)
    elif action == "wait":
        ctx.wait_for_selector(step["selector"], timeout=timeout, state="visible")
    elif action == "sleep":
        time.sleep(float(step["seconds"]))
    elif action == "select_seats":
        if step.get("selector"):
            ctx.wait_for_selector(step["selector"], timeout=timeout)
        n = select_seats(ctx, step)
        need = int(step.get("count", 1))
        if n < need:
            raise RuntimeError(f"원하는 좌석 중 {n}/{need}석만 선택 가능 — 직접 골라주세요")
    else:
        raise ValueError(f"알 수 없는 action: {action}")


# ───────────────────────── 명령 ─────────────────────────

def cmd_login(cfg: dict, args) -> None:
    state = Path(cfg.get("storage_state", "auth.json"))
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, executable_path=args.chromium)
        ctx = browser.new_context()
        page = ctx.new_page()
        page.goto(cfg.get("login_url") or cfg["start_url"])
        input("브라우저에서 직접 로그인한 뒤 여기서 Enter를 누르세요... ")
        ctx.storage_state(path=str(state))
        browser.close()
    print(f"세션 저장 완료: {state}  (이 파일은 비밀번호급이니 공유·커밋 금지)")


def cmd_run(cfg: dict, args) -> None:
    state = cfg.get("storage_state", "auth.json")
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=args.headless, executable_path=args.chromium, slow_mo=cfg.get("slow_mo_ms", 0)
        )
        ctx = browser.new_context(storage_state=state if Path(state).exists() else None)
        page = ctx.new_page()
        page.goto(cfg["start_url"], wait_until="domcontentloaded")

        try:
            wait_until_open(page, cfg)
            for step in cfg["steps"]:
                run_step(page, step)
            done = cfg.get("payment_ready_selector")
            if done:
                page.wait_for_selector(done, timeout=15_000)
            notify("결제창 도착! 지금 직접 결제하세요.")
        except Exception as e:
            notify(f"자동 진행 중단: {e}\n브라우저에서 직접 이어서 진행하세요.")

        if args.headless:
            browser.close()
            return
        # 사람이 결제할 수 있게 브라우저를 열어둠
        input("결제를 마치면 Enter를 눌러 종료... ")
        browser.close()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["login", "run"])
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--headless", action="store_true", help="테스트용. 실제 예매 때는 쓰지 마세요")
    ap.add_argument("--chromium", default=os.environ.get("CHROMIUM_PATH"), help="크롬 실행파일 경로(선택)")
    args = ap.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    {"login": cmd_login, "run": cmd_run}[args.command](cfg, args)


if __name__ == "__main__":
    sys.exit(main())
