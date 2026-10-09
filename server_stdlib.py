# -*- coding: utf-8 -*-
"""
Servidor do Xadrez — Edição de Clube, SEM dependências externas.

Usa apenas a biblioteca padrão do Python (http.server). Serve o frontend de
`web/`, a mesma API JSON do server.py (FastAPI) e o **WebSocket** de
multiplayer em `/ws` (handshake e frames feitos à mão aqui).

Rodar:
    python server_stdlib.py
    # abre http://127.0.0.1:8000
"""

import base64
import hashlib
import json
import mimetypes
import os
import queue
import re
import struct
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, unquote

from game_session import Session, GameError, LEVELS
from multiplayer import LOBBY
from ranking import RANKING

HOST = "127.0.0.1"
PORT = 8000
WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")

GAMES: dict[str, Session] = {}
STATE_RE = re.compile(r"^/api/state/([0-9a-fA-F]+)$")
PLAYER_RE = re.compile(r"^/api/player/([^/]+)$")

# ------------------------- WebSocket: protocolo mínimo ----------------------
WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
OP_CONT, OP_TEXT, OP_BIN, OP_CLOSE, OP_PING, OP_PONG = 0x0, 0x1, 0x2, 0x8, 0x9, 0xA


def _read_exact(rfile, n):
    if n <= 0:
        return b""
    buf = rfile.read(n)
    if buf is None or len(buf) < n:
        raise ConnectionError("conexão encerrada")
    return buf


def read_frame(rfile):
    """Lê um frame do cliente (frames do cliente sempre vêm mascarados)."""
    b = _read_exact(rfile, 2)
    opcode = b[0] & 0x0F
    masked = b[1] & 0x80
    length = b[1] & 0x7F
    if length == 126:
        length = struct.unpack(">H", _read_exact(rfile, 2))[0]
    elif length == 127:
        length = struct.unpack(">Q", _read_exact(rfile, 8))[0]
    mask = _read_exact(rfile, 4) if masked else b""
    payload = _read_exact(rfile, length)
    if masked:
        payload = bytes(c ^ mask[i & 3] for i, c in enumerate(payload))
    return opcode, payload


def write_frame(wfile, data, opcode=OP_TEXT):
    """Escreve um frame do servidor (sem máscara)."""
    header = bytearray()
    header.append(0x80 | opcode)
    n = len(data)
    if n < 126:
        header.append(n)
    elif n < 65536:
        header.append(126)
        header += struct.pack(">H", n)
    else:
        header.append(127)
        header += struct.pack(">Q", n)
    wfile.write(bytes(header) + data)
    wfile.flush()


class StdlibConnection:
    """Conexão WebSocket para o servidor em threads.

    `send_json` apenas enfileira: a escrita real acontece numa thread própria,
    então uma sala nunca fica presa esperando um cliente lento.
    """

    def __init__(self, wfile, wlock):
        self.wfile = wfile
        self.wlock = wlock
        self.room = None
        self.color = None
        self.name = None
        self._closed = False
        self._queue = queue.Queue()
        self._writer = threading.Thread(target=self._pump, daemon=True)
        self._writer.start()

    def _pump(self):
        while True:
            data = self._queue.get()
            if data is None:
                break
            try:
                with self.wlock:
                    write_frame(self.wfile, data, OP_TEXT)
            except (OSError, ValueError):  # cliente foi embora no meio do flush
                break

    def send_json(self, obj):
        if self._closed:
            return
        self._queue.put(json.dumps(obj, ensure_ascii=False).encode("utf-8"))

    def send_pong(self, payload):
        with self.wlock:
            write_frame(self.wfile, payload, OP_PONG)

    def stop(self):
        self._closed = True
        self._queue.put(None)


class Handler(BaseHTTPRequestHandler):
    server_version = "XadrezClube/1.0"
    protocol_version = "HTTP/1.1"

    def setup(self):
        super().setup()
        self.wlock = threading.Lock()

    # ---- utilidades --------------------------------------------------------
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

    def _send_json(self, obj, status=200):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self._cors()
        self.end_headers()
        self.wfile.write(data)

    def _error(self, status, message):
        self._send_json({"detail": message}, status)

    def _body(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = 0
        if n <= 0:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode("utf-8") or "{}")
        except (ValueError, UnicodeDecodeError):
            raise GameError("Corpo JSON inválido")

    def _game(self, gid):
        game = GAMES.get(gid)
        if not game:
            raise GameError("Partida não encontrada (servidor reiniciou?)")
        return game

    # ---- CORS preflight ----------------------------------------------------
    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    # ---- GET ---------------------------------------------------------------
    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/ws" and self.headers.get("Upgrade", "").lower() == "websocket":
            return self._handle_websocket()

        if path == "/api/health":
            return self._send_json({"ok": True, "games": len(GAMES), "lobby": LOBBY.stats()})

        if path == "/api/ranking":
            qs = parse_qs(urlparse(self.path).query)
            try:
                limit = int(qs.get("limit", ["50"])[0])
            except ValueError:
                limit = 50
            return self._send_json(RANKING.top(limit))

        m = PLAYER_RE.match(path)
        if m:
            prof = RANKING.get(unquote(m.group(1)))
            if not prof:
                return self._error(404, "Jogador não encontrado")
            return self._send_json(prof)

        m = STATE_RE.match(path)
        if m:
            try:
                game = self._game(m.group(1))
            except GameError as exc:
                return self._error(404, str(exc))
            return self._send_json({"state": game.state()})

        if path.startswith("/api/"):
            return self._error(404, "Rota não encontrada")

        return self._serve_static(path)

    # ---- POST --------------------------------------------------------------
    def do_POST(self):
        path = urlparse(self.path).path
        try:
            body = self._body()

            if path == "/api/new":
                gid = uuid.uuid4().hex
                game = Session(body.get("level", "medium"),
                               body.get("human_color", "w"))
                GAMES[gid] = game
                return self._send_json({"game_id": gid, "state": game.state()})

            if path == "/api/move":
                game = self._game(body.get("game_id", ""))
                if game.game_over:
                    raise GameError("Partida encerrada")
                if game.engine.turn != game.human_color:
                    raise GameError("Não é a vez do humano")
                move = body.get("move")
                if not isinstance(move, list) or len(move) != 4:
                    raise GameError("Formato de jogada inválido")
                game.apply(move)
                return self._send_json({"state": game.state(anim=game.last_anim)})

            if path == "/api/ai":
                game = self._game(body.get("game_id", ""))
                mv = game.ai_move()
                return self._send_json({
                    "state": game.state(anim=game.last_anim if mv else None),
                    "ai_move": mv})

            if path == "/api/undo":
                game = self._game(body.get("game_id", ""))
                game.undo()
                return self._send_json({"state": game.state()})

            if path == "/api/level":
                game = self._game(body.get("game_id", ""))
                if body.get("level") in LEVELS:
                    game.level = body["level"]
                return self._send_json({"state": game.state()})

            return self._error(404, "Rota não encontrada")

        except GameError as exc:
            return self._error(400, str(exc))
        except Exception as exc:  # noqa: BLE001 - devolve 500 em vez de derrubar
            return self._error(500, "Erro interno: %s" % exc)

    # ---- WebSocket ---------------------------------------------------------
    def _handle_websocket(self):
        key = self.headers.get("Sec-WebSocket-Key")
        if not key:
            return self._error(400, "Handshake WebSocket inválido")

        accept = base64.b64encode(
            hashlib.sha1((key + WS_GUID).encode("ascii")).digest()).decode("ascii")

        self.send_response(101)
        self.send_header("Upgrade", "websocket")
        self.send_header("Connection", "Upgrade")
        self.send_header("Sec-WebSocket-Accept", accept)
        self.end_headers()
        self.wfile.flush()
        self.close_connection = True  # não tenta ler outro HTTP depois do WS

        conn = StdlibConnection(self.wfile, self.wlock)
        try:
            while True:
                try:
                    opcode, payload = read_frame(self.rfile)
                except (ConnectionError, OSError):
                    break
                if opcode == OP_CLOSE:
                    break
                if opcode == OP_PING:
                    conn.send_pong(payload)
                    continue
                if opcode in (OP_PONG, OP_CONT, OP_BIN):
                    continue
                if opcode == OP_TEXT:
                    try:
                        msg = json.loads(payload.decode("utf-8"))
                    except (ValueError, UnicodeDecodeError):
                        continue
                    try:
                        LOBBY.handle(conn, msg)
                    except Exception:  # noqa: BLE001 - uma msg ruim não derruba a conexão
                        pass
        finally:
            conn.stop()
            LOBBY.disconnect(conn)

    # ---- arquivos estáticos ------------------------------------------------
    def _serve_static(self, path):
        if path == "/":
            path = "/index.html"
        rel = path.lstrip("/")
        full = os.path.normpath(os.path.join(WEB_DIR, rel))
        if not full.startswith(WEB_DIR) or not os.path.isfile(full):
            return self._error(404, "Arquivo não encontrado")
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype == "application/javascript":
            ctype += "; charset=utf-8"
        with open(full, "rb") as fh:
            data = fh.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    # ---- log enxuto --------------------------------------------------------
    def log_message(self, fmt, *args):  # noqa: A003
        return


def main():
    if not os.path.isdir(WEB_DIR):
        print("[AVISO] Pasta 'web' não encontrada em %s" % WEB_DIR)
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    print("\n  Xadrez — Edição de Clube  (servidor sem dependências)")
    print("  Abra no navegador:  http://%s:%d" % (HOST, PORT))
    print("  Multiplayer (WebSocket):  ws://%s:%d/ws" % (HOST, PORT))
    print("  Para parar:         Ctrl + C\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor encerrado.")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
