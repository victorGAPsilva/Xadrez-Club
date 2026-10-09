# -*- coding: utf-8 -*-
"""
Servidor FastAPI do Xadrez — Edição de Clube.

O motor de regras e a IA vivem em `chess_core.py`; a sessão de partida em
`game_session.py`. Este módulo expõe a API JSON e, opcionalmente, serve o
frontend de `web/`.

Rodar local:
    pip install -r requirements.txt
    uvicorn server:app --reload
    # abre http://127.0.0.1:8000

Se você só quer TESTAR sem instalar nada, use o servidor sem dependências:
    python server_stdlib.py
"""

import asyncio
import os
import uuid

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from game_session import Session, GameError
from multiplayer import LOBBY
from ranking import RANKING

LEVELS = {"easy", "medium", "hard"}

app = FastAPI(title="Xadrez — Edição de Clube", version="1.0")

# CORS liberado para permitir o frontend hospedado no GitHub Pages
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

GAMES: dict[str, Session] = {}


def get_game(game_id: str) -> Session:
    game = GAMES.get(game_id)
    if not game:
        raise HTTPException(404, "Partida não encontrada (servidor reiniciou?)")
    return game


# ---------------------------------------------------------------------------
# Modelos de requisição
# ---------------------------------------------------------------------------
class NewGameIn(BaseModel):
    level: str = "medium"
    human_color: str = "w"


class MoveIn(BaseModel):
    game_id: str
    move: list[int]  # [from_row, from_col, to_row, to_col]


class GameIn(BaseModel):
    game_id: str


class LevelIn(BaseModel):
    game_id: str
    level: str


# ---------------------------------------------------------------------------
# Rotas da API
# ---------------------------------------------------------------------------
@app.get("/api/health")
def health():
    return {"ok": True, "games": len(GAMES), "lobby": LOBBY.stats()}


@app.get("/api/ranking")
def ranking_top(limit: int = 50):
    return RANKING.top(limit)


@app.get("/api/player/{pid}")
def player(pid: str):
    prof = RANKING.get(pid)
    if not prof:
        raise HTTPException(404, "Jogador não encontrado")
    return prof


@app.post("/api/new")
def new_game(body: NewGameIn):
    gid = uuid.uuid4().hex
    game = Session(body.level, body.human_color)
    GAMES[gid] = game
    return {"game_id": gid, "state": game.state()}


@app.get("/api/state/{game_id}")
def state(game_id: str):
    return {"state": get_game(game_id).state()}


@app.post("/api/move")
def move(body: MoveIn):
    game = get_game(body.game_id)
    if game.game_over:
        raise HTTPException(400, "Partida encerrada")
    if game.engine.turn != game.human_color:
        raise HTTPException(400, "Não é a vez do humano")
    if len(body.move) != 4:
        raise HTTPException(400, "Formato de jogada inválido")
    try:
        game.apply(body.move)
    except GameError as exc:
        raise HTTPException(400, str(exc))
    return {"state": game.state(anim=game.last_anim)}


@app.post("/api/ai")
def ai(body: GameIn):
    game = get_game(body.game_id)
    mv = game.ai_move()
    return {"state": game.state(anim=game.last_anim if mv else None),
            "ai_move": mv}


@app.post("/api/undo")
def undo(body: GameIn):
    game = get_game(body.game_id)
    game.undo()
    return {"state": game.state()}


@app.post("/api/level")
def set_level(body: LevelIn):
    game = get_game(body.game_id)
    if body.level in LEVELS:
        game.level = body.level
    return {"state": game.state()}


# ---------------------------------------------------------------------------
# Multiplayer (WebSocket) — usa a MESMA lógica de salas do servidor stdlib
# ---------------------------------------------------------------------------
class ASGIConnection:
    """Adapta o WebSocket do Starlette à interface que `multiplayer` espera.

    `send_json` apenas coloca na fila; um task de envio escreve de verdade,
    preservando a ordem e sem bloquear a sala.
    """

    def __init__(self, ws: WebSocket):
        self.ws = ws
        self.room = None
        self.color = None
        self.name = None
        self._queue: asyncio.Queue = asyncio.Queue()
        self._task = None

    async def start(self):
        self._task = asyncio.create_task(self._pump())

    async def _pump(self):
        while True:
            obj = await self._queue.get()
            if obj is None:
                break
            try:
                await self.ws.send_json(obj)
            except Exception:  # noqa: BLE001 - cliente caiu
                break

    def send_json(self, obj):
        self._queue.put_nowait(obj)

    async def stop(self):
        self._queue.put_nowait(None)
        if self._task:
            try:
                await self._task
            except Exception:  # noqa: BLE001
                pass


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    conn = ASGIConnection(ws)
    await conn.start()
    try:
        while True:
            msg = await ws.receive_json()
            try:
                LOBBY.handle(conn, msg)
            except Exception:  # noqa: BLE001 - uma msg ruim não derruba a conexão
                pass
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001
        pass
    finally:
        await conn.stop()
        LOBBY.disconnect(conn)


# ---------------------------------------------------------------------------
# Frontend estático (opcional: também roda no GitHub Pages separadamente)
# ---------------------------------------------------------------------------
WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")

if os.path.isdir(WEB_DIR):
    @app.get("/")
    def index():
        return FileResponse(os.path.join(WEB_DIR, "index.html"))

    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")


# Permite rodar direto:  python server.py
if __name__ == "__main__":
    import uvicorn

    print("\n  Xadrez — Edição de Clube (FastAPI)")
    print("  Abra no navegador:  http://127.0.0.1:8000")
    print("  Para parar:         Ctrl + C\n")
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=False)
