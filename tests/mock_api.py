"""watch.py 테스트용 모의 상영시간표 API. 3번째 조회부터 회차가 '오픈'됨.
지점코드는 일부러 두 번째 형식(1|101|2004)만 응답하게 해서 자동 탐색도 확인."""
import http.server, json, sys, urllib.parse
N = {"n": 0}
ITEMS = [
    ("200405", "5관", "어벤져스: 둠스데이", "11:30", 150),   # 12시 전 → 제외
    ("200405", "5관", "어벤져스: 둠스데이", "13:10", 2),     # 잔여 부족 → 제외
    ("200405", "5관", "어벤져스: 둠스데이", "16:40", 150),   # ✔
    ("200405", "5관", "어벤져스: 둠스데이", "19:50", 150),   # ✔
    ("200403", "3관", "어벤져스: 둠스데이", "12:10", 150),   # 다른 관 → 제외
    ("200405", "5관", "다른 영화", "14:00", 150),            # 다른 영화 → 제외
]
class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        q = urllib.parse.parse_qs(self.rfile.read(int(self.headers["Content-Length"])).decode())
        p = json.loads(q["paramList"][0])
        items = []
        if p["cinemaID"] == "1|101|2004":
            N["n"] += 1
            if N["n"] >= 3:
                items = [dict(ScreenID=int(s), ScreenNameKR=sn, MovieNameKR=m, StartTime=t,
                              EndTime="", BookingSeatCount=c, TotalSeatCount=150) for s, sn, m, t, c in ITEMS]
        b = json.dumps({"IsOK": "true", "PlaySeqs": {"Items": items}}).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(b)
http.server.HTTPServer(("127.0.0.1", int(sys.argv[1]) if len(sys.argv) > 1 else 8767), H).serve_forever()
