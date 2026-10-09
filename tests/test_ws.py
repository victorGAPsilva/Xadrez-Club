import base64
import json
import os
import socket
import struct
import sys
import threading
from http.server import ThreadingHTTPServer

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
    req = (
        "GET %s HTTP/1.1\r\nHost: %s\r\nUpgrade: websocket\r\n"
        "Connection: Upgrade\r\nSec-WebSocket-Key: %s\r\n"
        "Sec-WebSocket-Version: 13\r\n\r\n" % (path, host, key)
    )
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
    header = bytearray([0x81])  # FIN + text
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
    """Lê tudo que chegar dentro da janela e devolve a lista de mensagens JSON."""
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


# ------------------------------- servidor ----------------------------------
httpd = ThreadingHTTPServer(("127.0.0.1", 0), ss.Handler)
port = httpd.server_address[1]
threading.Thread(target=httpd.serve_forever, daemon=True).start()

c1 = c2 = c3 = None
try:
    # 1) cria sala
    c1 = ws_connect("127.0.0.1", port)
    ws_send(c1, {"type": "create", "name": "Ana"})
    msgs = collect(c1)
    created = last(msgs, "created")
    assert created, msgs
    code = created["code"]
    assert last(msgs, "room")["you"] == "w"
    print("c1 criou a sala", code)

    # 2) segundo entra
    c2 = ws_connect("127.0.0.1", port)
    ws_send(c2, {"type": "join", "code": code, "name": "Bia"})
    msgs2 = collect(c2)
    assert last(msgs2, "room")["you"] == "b", msgs2
    assert last(msgs2, "room")["status"] == "playing"
    # c1 precisa saber que encheu
    assert last(collect(c1), "room")["status"] == "playing"
    print("c2 entrou como pretas; partida iniciada")

    # 3) lance das brancas chega nos dois
    ws_send(c1, {"type": "move", "move": [6, 4, 4, 4]})
    m1 = last(collect(c1), "state")
    m2 = last(collect(c2), "state")
    assert m1["state"]["history"][-1]["san"] == "e4"
    assert m2["state"]["history"][-1]["san"] == "e4"
    assert m2["state"]["human_color"] == "b"
    assert m2["state"]["anim"]["to"] == [4, 4]
    print("e2-e4 transmitido aos dois jogadores")

    # 4) lance das pretas
    ws_send(c2, {"type": "move", "move": [1, 4, 3, 4]})
    m1 = last(collect(c1), "state")
    assert m1["state"]["history"][-1]["san"] == "e5", m1["state"]["history"]
    print("e7-e5 transmitido ao oponente")

    # 5) fora de vez -> erro só para quem mandou (é vez das brancas)
    ws_send(c2, {"type": "move", "move": [0, 6, 2, 5]})
    err = last(collect(c2), "error")
    assert err and "vez" in err["message"].lower(), err
    print("erro de vez recebido:", err["message"])

    # 6) espectador
    c3 = ws_connect("127.0.0.1", port)
    ws_send(c3, {"type": "join", "code": code, "name": "Cid"})
    m3 = collect(c3)
    assert last(m3, "room")["you"] == "spec", m3
    ws_send(c3, {"type": "move", "move": [6, 0, 5, 0]})
    assert last(collect(c3), "error"), "espectador não deveria jogar"
    print("espectador recebe estado e não pode jogar")

    # 7) chat
    ws_send(c1, {"type": "chat", "text": "boa partida!"})
    chat = last(collect(c2), "chat")
    assert chat and chat["text"] == "boa partida!" and chat["name"] == "Ana"
    print("chat entregue ao oponente")

    # 8) ping/pong
    ws_send(c1, {"type": "ping"})
    assert last(collect(c1), "pong"), "deveria responder pong"
    print("ping/pong OK")

    # 9) sair: o outro é avisado
    ws_send(c1, {"type": "leave"})
    sysmsgs = collect(c2)
    assert any(m.get("type") == "sys" and "saiu" in m["text"] for m in sysmsgs), sysmsgs
    print("saída notificada:", [m["text"] for m in sysmsgs if m["type"] == "sys"])

    # 10) sala inexistente
    ws_send(c2, {"type": "join", "code": "ZZZZ"})
    assert last(collect(c2), "error"), "sala inexistente deveria dar erro"
    print("sala inexistente rejeitada")

    print("TODOS OS TESTES DE WEBSOCKET (e2e real) PASSARAM")
finally:
    for s in (c1, c2, c3):
        try:
            if s:
                s.close()
        except OSError:
            pass
    httpd.shutdown()
