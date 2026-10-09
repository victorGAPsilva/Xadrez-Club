import base64
import json
import os
import socket
import struct
import sys
import tempfile
import threading
import urllib.request
from http.server import ThreadingHTTPServer

# Banco em arquivo temporário, isolado do de verdade
os.environ["XADREZ_DB"] = os.path.join(tempfile.gettempdir(), "rank_e2e.db")
if os.path.exists(os.path.join(tempfile.gettempdir(), "rank_e2e.db")):
    os.remove(os.path.join(tempfile.gettempdir(), "rank_e2e.db"))

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server_stdlib as ss

# ------------------------- cliente WebSocket mínimo -------------------------
def recv_exact(sock, n):
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("fechou")
        buf += chunk
    return buf


def ws_connect(host, port, path="/ws"):
    s = socket.create_connection((host, port), timeout=5)
    key = base64.b64encode(os.urandom(16)).decode()
    req = ("GET %s HTTP/1.1\r\nHost: %s\r\nUpgrade: websocket\r\n"
           "Connection: Upgrade\r\nSec-WebSocket-Key: %s\r\n"
           "Sec-WebSocket-Version: 13\r\n\r\n" % (path, host, key))
    s.sendall(req.encode())
    data = b""
    while b"\r\n\r\n" not in data:
        data += s.recv(1)
    assert b"101" in data.split(b"\r\n")[0], data
    return s


def ws_send(sock, obj):
    data = json.dumps(obj).encode()
    key = os.urandom(4)
    masked = bytes(b ^ key[i & 3] for i, b in enumerate(data))
    header = bytearray([0x81])
    n = len(data)
    if n < 126:
        header.append(0x80 | n)
    elif n < 65536:
        header.append(0x80 | 126)
        header += struct.pack(">H", n)
    else:
        header.append(0x80 | 127)
        header += struct.pack(">Q", n)
    sock.sendall(bytes(header) + key + masked)


def ws_recv(sock):
    b = recv_exact(sock, 2)
    opcode = b[0] & 0x0F
    length = b[1] & 0x7F
    if length == 126:
        length = struct.unpack(">H", recv_exact(sock, 2))[0]
    elif length == 127:
        length = struct.unpack(">Q", recv_exact(sock, 8))[0]
    payload = recv_exact(sock, length) if length else b""
    return opcode, payload


def collect(sock, timeout=0.7):
    sock.settimeout(timeout)
    out = []
    try:
        while True:
            op, payload = ws_recv(sock)
            if op == 0x1:
                out.append(json.loads(payload.decode()))
            elif op == 0x8:
                break
    except (socket.timeout, ConnectionError, OSError):
        pass
    return out


def last(msgs, t):
    for m in reversed(msgs):
        if m.get("type") == t:
            return m
    return None


def http_json(path):
    with urllib.request.urlopen("http://127.0.0.1:%d%s" % (port, path), timeout=5) as r:
        return json.loads(r.read())


httpd = ThreadingHTTPServer(("127.0.0.1", 0), ss.Handler)
port = httpd.server_address[1]
threading.Thread(target=httpd.serve_forever, daemon=True).start()

conns = []
try:
    # ---- Partida 1: mate do tolo, valendo ELO ----
    c1 = ws_connect("127.0.0.1", port)
    c2 = ws_connect("127.0.0.1", port)
    conns += [c1, c2]
    ws_send(c1, {"type": "create", "name": "Ana", "pid": "P1"})
    code1 = last(collect(c1), "created")["code"]
    ws_send(c2, {"type": "join", "code": code1,
                 "name": "Bia", "pid": "P2"})
    collect(c2)
    collect(c1)

    # 1.f3 e5 2.g4 Qh4# — um lance por vez, aguardando o servidor processar
    plies = [(c1, [6,5,5,5]), (c2, [1,4,3,4]), (c1, [6,6,4,6]), (c2, [0,3,4,7])]
    msgs1, msgs2 = [], []
    for who, mv in plies:
        ws_send(who, {"type": "move", "move": mv})
        msgs1 += collect(c1)
        msgs2 += collect(c2)
    st1 = last(msgs1, "state")["state"]
    st2 = last(msgs2, "state")["state"]
    assert st1["game_over"] and st1["result"].startswith("Xeque-mate"), st1["result"]
    assert st2["winner"] == "b"
    print("xeque-mate (mate do tolo) OK:", st1["result"])

    r1 = last(msgs1, "rating")
    r2 = last(msgs2, "rating")
    assert r1 and r2, (msgs1, msgs2)
    assert r1["delta"] == -16 and r2["delta"] == 16, (r1, r2)
    assert r1["profile"]["games"] == 1 and r2["profile"]["wins"] == 1
    print("ELO aplicado:", r1["profile"]["name"], r1["profile"]["rating"],
          "/", r2["profile"]["name"], r2["profile"]["rating"])

    # ---- /api/ranking e /api/player ----
    top = http_json("/api/ranking")
    assert top["total"] == 2
    assert top["top"][0]["id"] == "P2" and top["top"][0]["rating"] == 1216
    assert top["top"][1]["id"] == "P1" and top["top"][1]["rating"] == 1184
    pl = http_json("/api/player/P1")
    assert pl["games"] == 1 and pl["losses"] == 1 and pl["rank"] == 2
    print("ranking HTTP OK:", [(p["name"], p["rating"]) for p in top["top"]])

    # ---- Partida 2: abandono -> W.O. do adversário ----
    c3 = ws_connect("127.0.0.1", port)
    c4 = ws_connect("127.0.0.1", port)
    conns += [c3, c4]
    ws_send(c3, {"type": "create", "name": "Cid", "pid": "P3"})
    code3 = last(collect(c3), "created")["code"]
    ws_send(c4, {"type": "join", "code": code3,
                 "name": "Duda", "pid": "P4"})
    collect(c4)
    collect(c3)

    ws_send(c3, {"type": "move", "move": [6, 5, 5, 5]})  # f3 (começou)
    collect(c3); collect(c4)
    ws_send(c3, {"type": "leave"})                        # brancas abandonam
    msgs4 = collect(c4)
    sysmsgs = [m["text"] for m in msgs4 if m["type"] == "sys"]
    assert any("desistência" in t for t in sysmsgs), sysmsgs
    r4 = last(msgs4, "rating")
    assert r4 and r4["delta"] > 0 and r4["profile"]["wins"] == 1
    wo = http_json("/api/player/P3")
    assert wo["games"] == 1 and wo["losses"] == 1, wo
    print("W.O. por desistência OK:", sysmsgs)

    r3prof = last(collect(c3), "rating")
    print("ranking após W.O.:", [p["name"] for p in http_json("/api/ranking")["top"][:2]])

    print("TODOS OS TESTES DE RANKING (e2e web) PASSARAM")
finally:
    for s in conns:
        try:
            if s:
                s.close()
        except OSError:
            pass
    httpd.shutdown()