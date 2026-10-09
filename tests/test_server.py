import sys, types, json, os

# ---- stubs mínimos de fastapi/pydantic para importar server.py ----
class HTTPException(Exception):
    def __init__(self, status_code, detail=""):
        self.status_code, self.detail = status_code, detail
        super().__init__(detail)

class BaseModel:
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)

class _App:
    def __init__(self, *a, **k): pass
    def add_middleware(self, *a, **k): pass
    def get(self, *a, **k):
        return lambda f: f
    def post(self, *a, **k):
        return lambda f: f
    def websocket(self, *a, **k):
        return lambda f: f
    def mount(self, *a, **k): pass

fa = types.ModuleType("fastapi")
fa.FastAPI = _App
fa.HTTPException = HTTPException
fa.WebSocket = object
fa.WebSocketDisconnect = type("WebSocketDisconnect", (Exception,), {})
fa.middleware = types.ModuleType("fastapi.middleware")
fa.middleware.cors = types.ModuleType("fastapi.middleware.cors")
fa.middleware.cors.CORSMiddleware = object
fa.responses = types.ModuleType("fastapi.responses")
fa.responses.FileResponse = type("FileResponse", (), {"__init__": lambda self, *a, **k: None})
fa.staticfiles = types.ModuleType("fastapi.staticfiles")
fa.staticfiles.StaticFiles = type("StaticFiles", (), {"__init__": lambda self, *a, **k: None})
sys.modules["fastapi"] = fa
sys.modules["fastapi.middleware"] = fa.middleware
sys.modules["fastapi.middleware.cors"] = fa.middleware.cors
sys.modules["fastapi.responses"] = fa.responses
sys.modules["fastapi.staticfiles"] = fa.staticfiles
pd = types.ModuleType("pydantic")
pd.BaseModel = BaseModel
sys.modules["pydantic"] = pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server

# 1) health
assert server.health() == {"ok": True, "games": 0, "lobby": {"rooms": 0, "queued": 0}}

# 2) novo jogo + estrutura do estado
r = server.new_game(server.NewGameIn(level="medium", human_color="w"))
gid = r["game_id"]
st = r["state"]
assert st["board"][6][4] == "wP" and st["turn"] == "w"
assert len(st["legal"]) == 20
json.dumps(st)  # serializável
print("novo jogo OK; lances legais:", len(st["legal"]))

# 3) lance humano e2-e4
r = server.move(server.MoveIn(game_id=gid, move=[6, 4, 4, 4]))
st = r["state"]
assert st["board"][4][4] == "wP" and st["history"][-1]["san"] == "e4"
assert st["anim"]["piece"] == "wP" and st["anim"]["from"] == [6, 4] and st["anim"]["to"] == [4, 4]
json.dumps(st)
print("lance humano e2-e4 OK; anim:", st["anim"])

# 4) lance da IA responde
r = server.ai(server.GameIn(game_id=gid))
st = r["state"]
assert st["turn"] == "w", "após a IA deveria ser vez das brancas"
assert r["ai_move"] is not None
json.dumps(st)
print("IA respondeu:", r["ai_move"], "| SAN:", st["history"][-1]["san"])

# 5) jogada ilegal é rejeitada
try:
    server.move(server.MoveIn(game_id=gid, move=[7, 0, 7, 1]))
    raise SystemExit("FALHOU: jogada ilegal aceita")
except HTTPException as e:
    print("jogada ilegal rejeitada:", e.detail)

# 6) jogar fora do turno é rejeitado (é vez das brancas, tentar mover peça preta)
try:
    server.move(server.MoveIn(game_id=gid, move=[1, 4, 3, 4]))
    raise SystemExit("FALHOU: lance fora do turno aceito")
except HTTPException as e:
    print("lance fora do turno rejeitado:", e.detail)

# 7) undo volta ao início (desfaz o par humano+IA)
r = server.undo(server.GameIn(game_id=gid))
st = r["state"]
assert st["history"] == [] and st["turn"] == "w"
json.dumps(st)
print("undo OK; histórico vazio:", st["history"] == [])

# 8) humano de pretas -> IA (brancas) abre
r = server.new_game(server.NewGameIn(level="easy", human_color="b"))
gid2 = r["game_id"]
assert r["state"]["turn"] == "w" and r["state"]["ai_color"] == "w"
r = server.ai(server.GameIn(game_id=gid2))
st = r["state"]
assert st["turn"] == "b"
print("humano de pretas: IA abriu com", r["ai_move"])

# 9) nível é atualizado
r = server.set_level(server.LevelIn(game_id=gid2, level="hard"))
assert r["state"]["level"] == "hard"
print("nível atualizado OK")

# 10) partida inexistente -> 404
try:
    server.state("naoexiste")
    raise SystemExit("FALHOU: deveria dar 404")
except HTTPException as e:
    print("partida inexistente:", e.status_code, e.detail)

print("TODOS OS TESTES DO SERVIDOR PASSARAM")
