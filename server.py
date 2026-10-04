"""Quiz Buzzer server (Python 3.8+, standard library only).
Run:  HOST_PIN=4821 python server.py
"""
import hmac, json, os, queue, socket, sys, threading, time
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

BASE = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ.get("PORT", 3000))
PIN = str(os.environ.get("HOST_PIN", "1234"))
if PIN == "1234" and (os.environ.get("APP_ENV") == "production" or os.environ.get("RENDER")):
    sys.exit("Set a HOST_PIN environment variable before deploying.")

def lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "localhost"

JOIN = os.environ.get("PUBLIC_URL") or os.environ.get("RENDER_EXTERNAL_URL") or "http://%s:%d/" % (lan_ip(), PORT)

lock = threading.Lock()
game = {"open": False, "round": 0}
presses = []          # [{cid, name, at}] in arrival order
scores = {}           # team name -> points
players = []          # [(cid, queue)]
hosts = []            # [queue]

def player_view(cid):
    m = next((p for p in presses if p["cid"] == cid), None)
    return {"open": game["open"], "round": game["round"], "pressed": bool(m), "name": m["name"] if m else ""}

def host_view():
    t0 = presses[0]["at"] if presses else 0
    return {"join": JOIN, "open": game["open"], "round": game["round"],
            "presses": [{"name": p["name"], "ms": p["at"] - t0} for p in presses],
            "scores": [{"name": n, "score": s} for n, s in scores.items()]}

def push_all():                      # call while holding `lock`
    for cid, q in players:
        q.put(player_view(cid))
    for q in hosts:
        q.put(host_view())

def pin_ok(p):
    return hmac.compare_digest(str(p or "").encode(), PIN.encode())

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def reply(self, code, obj=None, ctype="application/json"):
        body = (json.dumps(obj or {}) if ctype == "application/json" else obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def page(self, name):
        try:
            with open(os.path.join(BASE, "public", name), "rb") as f:
                data = f.read()
        except OSError:
            return self.reply(404, "Not found", "text/plain")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def stream(self, q, first, cleanup):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        try:
            self.wfile.write(b"retry: 2000\n\n")
            self.wfile.write(("data: " + json.dumps(first) + "\n\n").encode())
            self.wfile.flush()
            while True:
                try:
                    self.wfile.write(("data: " + json.dumps(q.get(timeout=20)) + "\n\n").encode())
                except queue.Empty:
                    self.wfile.write(b": ping\n\n")
                self.wfile.flush()
        except OSError:
            pass
        finally:
            cleanup()

    def do_GET(self):
        u = urlparse(self.path)
        qs = parse_qs(u.query)
        if u.path == "/health":
            return self.reply(200, "ok", "text/plain")
        if u.path == "/":
            return self.page("index.html")
        if u.path == "/host":
            return self.page("host.html")
        if u.path == "/events":
            cid = (qs.get("cid", [""])[0])[:80]
            q = queue.Queue()
            with lock:
                entry = (cid, q)
                players.append(entry)
                first = player_view(cid)
            return self.stream(q, first, lambda: self._drop(players, entry))
        if u.path == "/host/events":
            if not pin_ok(qs.get("pin", [""])[0]):
                self.send_response(401)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            q = queue.Queue()
            with lock:
                hosts.append(q)
                first = host_view()
            return self.stream(q, first, lambda: self._drop(hosts, q))
        self.reply(404, "Not found", "text/plain")

    @staticmethod
    def _drop(lst, item):
        with lock:
            if item in lst:
                lst.remove(item)

    def body(self):
        try:
            n = int(self.headers.get("Content-Length", 0))
            if n > 2048:
                return {}
            return json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            return {}

    def do_POST(self):
        path = urlparse(self.path).path
        b = self.body()
        if path == "/buzz":
            cid = str(b.get("cid", ""))[:80]
            name = str(b.get("name", "")).strip()[:24]
            if not cid or not name:
                return self.reply(400, {"error": "Enter your team name."})
            with lock:
                if not game["open"]:
                    return self.reply(409, {"error": "Buzzer is locked."})
                if any(p["cid"] == cid or p["name"].lower() == name.lower() for p in presses):
                    return self.reply(409, {"error": "Already buzzed."})
                presses.append({"cid": cid, "name": name, "at": int(time.time() * 1000)})  # order = arrival order
                push_all()
            return self.reply(200, {"ok": True})
        if path == "/host/action":
            if not pin_ok(b.get("pin")):
                return self.reply(401, {"error": "Wrong PIN"})
            a = b.get("action")
            with lock:
                if a == "open":
                    game["open"] = True
                    game["round"] = game["round"] or 1
                elif a == "lock":
                    game["open"] = False
                elif a == "new":
                    game["round"] += 1
                    presses.clear()
                    game["open"] = True
                elif a == "point" and b.get("name"):
                    n = str(b["name"])[:24]
                    try:
                        d = int(b.get("delta") or 1)
                    except (TypeError, ValueError):
                        d = 1
                    scores[n] = scores.get(n, 0) + d
                push_all()
            return self.reply(200, {"ok": True})
        self.reply(404, "Not found", "text/plain")

if __name__ == "__main__":
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    srv.daemon_threads = True
    print("Quiz Buzzer running. Host PIN:", PIN, "(default, change it with HOST_PIN)" if PIN == "1234" else "")
    print("Host page:  http://localhost:%d/host" % PORT)
    print("Teams join:", JOIN)
    srv.serve_forever()
