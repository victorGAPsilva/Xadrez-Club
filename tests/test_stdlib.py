import json, os
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server_stdlib as ss

# Sobe o servidor numa porta livre, em thread
httpd = ThreadingHTTPServer(("127.0.0.1", 0), ss.Handler)
port = httpd.server_address[1]
threading.Thread(target=httpd.serve_forever, daemon=True).start()
BASE = f"http://127.0.0.1:{port}"


def get(path):
    try:
        with urllib.request.urlopen(BASE + path, timeout=5) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def post(path, obj):
    data = json.dumps(obj).encode()
    req = urllib.request.Request(BASE + path, data=data,
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


try:
    # 1) health
    st, body = get("/api/health")
    assert st == 200 and json.loads(body)["ok"] is True
    print("health:", json.loads(body))

    # 2) index.html servido com o conteúdo certo
    st, body = get("/")
    assert st == 200 and "XADREZ" in body.decode("utf-8")
    print("index.html OK:", len(body), "bytes")

    # 3) assets estáticos
    for path in ("/style.css", "/app.js", "/config.js"):
        st, body = get(path)
        assert st == 200 and len(body) > 50, path
    print("assets (css/js) OK")

    # 4) novo jogo
    st, r = post("/api/new", {"level": "medium", "human_color": "w"})
    assert st == 200 and len(r["state"]["legal"]) == 20
    gid = r["game_id"]
    print("novo jogo:", gid[:8], "| legais:", len(r["state"]["legal"]))

    # 5) lance humano e2-e4
    st, r = post("/api/move", {"game_id": gid, "move": [6, 4, 4, 4]})
    assert st == 200 and r["state"]["history"][-1]["san"] == "e4"
    assert r["state"]["anim"]["to"] == [4, 4]
    print("e2-e4 OK | anim:", r["state"]["anim"])

    # 6) IA responde
    st, r = post("/api/ai", {"game_id": gid})
    assert st == 200 and r["state"]["turn"] == "w"
    print("IA:", r["ai_move"], "| SAN:", r["state"]["history"][-1]["san"])

    # 7) jogada ilegal -> 400
    st, r = post("/api/move", {"game_id": gid, "move": [7, 0, 7, 1]})
    assert st == 400, (st, r)
    print("ilegal rejeitada:", r["detail"])

    # 8) ler estado
    st, body = get(f"/api/state/{gid}")
    assert st == 200 and json.loads(body)["state"]["board"][4][4] == "wP"
    print("GET estado OK")

    # 9) undo
    st, r = post("/api/undo", {"game_id": gid})
    assert st == 200 and r["state"]["history"] == []
    print("undo OK -> histórico vazio")

    # 10) 404 em rota inexistente e em arquivo inexistente
    st, _ = get("/api/nao-existe")
    assert st == 404
    st, _ = get("/nao-existe.html")
    assert st == 404
    print("404 OK")

    # 11) path traversal bloqueado
    st, _ = get("/../server.py")
    assert st == 404
    print("path traversal bloqueado")

    # 12) jogo inexistente
    st, r = post("/api/ai", {"game_id": "0000000000"})
    assert st == 400
    print("jogo inexistente:", r["detail"])

    print("TODOS OS TESTES HTTP (stdlib) PASSARAM")
finally:
    httpd.shutdown()
