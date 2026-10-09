import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from multiplayer import Lobby, make_code


class FakeConn:
    def __init__(self, name=None):
        self.room = None
        self.color = None
        self.name = name
        self.sent = []

    def send_json(self, obj):
        self.sent.append(obj)

    def last(self, t):
        for m in reversed(self.sent):
            if m.get("type") == t:
                return m
        return None

    def clear(self):
        self.sent = []


# código usa só caracteres não ambíguos
assert len(make_code()) == 4
assert all(c in "ABCDEFGHJKLMNPQRSTUVWXYZ23456789" for c in make_code())

lob = Lobby()
a = FakeConn("Ana")
b = FakeConn("Bia")

# criação
lob.handle(a, {"type": "create", "name": "Ana"})
created = a.last("created")
assert created and created["code"], "faltou 'created'"
code = created["code"]
room = lob.rooms[code]
assert a.color == "w", a.color
assert room.status == "waiting"
assert a.last("room")["you"] == "w"

# entrada do segundo jogador
lob.handle(b, {"type": "join", "code": code, "name": "Bia"})
assert b.color == "b", b.color
assert room.status == "playing"
st_a = [m for m in a.sent if m["type"] == "state"][-1]["state"]
st_b = [m for m in b.sent if m["type"] == "state"][-1]["state"]
assert st_a["human_color"] == "w" and st_b["human_color"] == "b"
assert st_a["mode"] == "online" and st_a["ai_color"] is None
print("criar/entrar OK — sala", code, "| status", room.status)

# lance e2-e4 (brancas)
b.clear()
lob.handle(a, {"type": "move", "move": [6, 4, 4, 4]})
st = [m for m in b.sent if m["type"] == "state"][-1]["state"]
assert st["history"][-1]["san"] == "e4", st["history"]
assert st["anim"]["to"] == [4, 4]
print("lance transmitido ao oponente:", st["history"][-1]["san"])

# fora de vez
a.clear()
lob.handle(a, {"type": "move", "move": [1, 4, 3, 4]})
err = a.last("error")
assert err and "vez" in err["message"].lower(), err
print("fora de vez rejeitado:", err["message"])

# lance ilegal
b.clear()
lob.handle(b, {"type": "move", "move": [1, 0, 1, 1]})
assert b.last("error"), "lance ilegal deveria falhar"
print("lance ilegal rejeitado:", b.last("error")["message"])

# chat
b.clear()
lob.handle(a, {"type": "chat", "text": "boa!"})
assert b.last("chat")["text"] == "boa!"
assert b.last("chat")["name"] == "Ana"
print("chat OK")

# espectador não joga
c = FakeConn("Cid")
lob.handle(c, {"type": "join", "code": code, "name": "Cid"})
assert c.color is None, c.color
assert c.last("room")["you"] == "spec"
lob.handle(c, {"type": "move", "move": [6, 0, 5, 0]})
assert c.last("error"), "espectador não deveria jogar"
print("espectador OK")

# revanche exige fim de jogo
lob.handle(a, {"type": "rematch"})
assert a.last("error") and "andamento" in a.last("error")["message"]
print("revanche bloqueada em jogo ativo OK")

# força fim de jogo e testa revanche (troca de cores)
room.session.game_over = True
a.clear(); b.clear()
lob.handle(a, {"type": "rematch"})
assert b.last("sys") and "revanche" in b.last("sys")["text"].lower()
lob.handle(b, {"type": "rematch"})
assert room.session.game_over is False
assert a.color == "b" and b.color == "w", (a.color, b.color)
assert room.status == "playing"
print("revanche OK — cores trocadas")

# sair
lob.handle(a, {"type": "leave"})
assert a.room is None
print("sair OK")

# fila aleatória pareia dois
lob2 = Lobby()
x = FakeConn("X"); y = FakeConn("Y")
lob2.handle(x, {"type": "queue", "name": "X"})
assert x.last("queued"), "deveria avisar que entrou na fila"
lob2.handle(y, {"type": "queue", "name": "Y"})
assert x.room is not None and x.room is y.room
assert x.color == "w" and y.color == "b"
print("fila aleatória OK — sala", x.room.code)

print("TODOS OS TESTES DE MULTIPLAYER (lógica) PASSARAM")
