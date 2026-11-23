"""롯데 모의 서버: 로그인/예매/좌석/결제 페이지 + 상영시간표 API(3번째 호출부터 회차 오픈)."""
import json, http.server, urllib.parse
N = {"api": 0}
PAGES = {
"/": '<a href="/login">로그인</a>',
"/login": '''<input id="userId"><input id="userPassword" type="password">
<button onclick="if(userId.value&&userPassword.value){document.cookie='li=1';location='/'}">로그인</button>''',
"/ticketing": '''<div>부산</div><div>부산본점</div><div>어벤져스: 둠스데이</div><div>16</div>
<button onclick="location='/seats'">11:30</button><button onclick="location='/seats'">13:10</button>
<button onclick="location='/seats'">16:40</button>''',
"/pay": '<h1>결제수단 선택</h1><p id="s"></p><script>s.textContent=location.search</script>',
}
def seats():
    sold = {"E7", "D7"}  # E6-8, D6-8 블록이 깨지도록
    out = ['<button id="adult3">3</button><div id="map">']
    for r in "ABCDEFGH":
        for c in range(1, 13):
            cls = "seat sold" if f"{r}{c}" in sold else "seat"
            out.append(f'<a class="{cls}" title="{r}{c}" onclick="this.classList.toggle(\'on\')">{r}{c}</a>')
        out.append("<br>")
    out.append('</div><button onclick="location=\'/pay?\'+[...document.querySelectorAll(\'.on\')].map(a=>a.title)">결제하기</button>')
    return "".join(out)
class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def send(self, body, ctype="text/html; charset=utf-8"):
        b = body.encode(); self.send_response(200); self.send_header("Content-Type", ctype); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        li = "li=1" in (self.headers.get("Cookie") or "")
        if path == "/seats": return self.send(seats())
        body = PAGES.get(path, "404")
        if path == "/" and li: body = '<a>로그아웃</a>'
        self.send('<meta charset="utf-8">' + body)
    def do_POST(self):
        n = int(self.headers["Content-Length"]); q = urllib.parse.parse_qs(self.rfile.read(n).decode())
        p = json.loads(q["paramList"][0]); N["api"] += 1
        items = []
        if N["api"] >= 3 and p["playDate"] == "2026-12-16":
            items = [
              {"ScreenID": 200405, "ScreenNameKR": "5관", "MovieNameKR": "어벤져스: 둠스데이", "StartTime": "11:30", "BookingSeatCount": 100},
              {"ScreenID": 200405, "ScreenNameKR": "5관", "MovieNameKR": "어벤져스: 둠스데이", "StartTime": "16:40", "BookingSeatCount": 100},
              {"ScreenID": 200405, "ScreenNameKR": "5관", "MovieNameKR": "어벤져스: 둠스데이", "StartTime": "13:10", "BookingSeatCount": 2},
              {"ScreenID": 200403, "ScreenNameKR": "3관", "MovieNameKR": "어벤져스: 둠스데이", "StartTime": "12:10", "BookingSeatCount": 100},
            ]
        self.send(json.dumps({"IsOK": "true", "PlaySeqs": {"Items": items}}), "application/json")
http.server.ThreadingHTTPServer(("127.0.0.1", 8766), H).serve_forever()
