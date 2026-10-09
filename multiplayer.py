# -*- coding: utf-8 -*-
"""
Salas de multiplayer do Xadrez — Edição de Clube.

Aqui vive a lógica de partida ONLINE, independente de transporte. Não importa
asyncio, fastapi nem sockets: trabalha com "conexões" que só precisam saber
`send_json(obj)`. Assim o mesmo cérebro roda no servidor sem dependências
(threads) e no FastAPI (asyncio).

Protocolo (cliente -> servidor)
    {type:"create", name?, pid?}           cria sala (você fica com as brancas)
    {type:"join", code, name?, pid?}       entra numa sala pelo código
    {type:"queue", name?, pid?}            entra na fila aleatória
    {type:"move", move:[fr,fc,tr,tc]}      faz um lance
    {type:"chat", text}                    manda uma mensagem
    {type:"rematch"}                       pede revanche
    {type:"leave"}                         sai da sala
    {type:"ping"}                          keep-alive

Protocolo (servidor -> cliente)
    {type:"created", code}                 sua sala foi criada
    {type:"room", code, you, status, names, seated, spectators}
    {type:"state", state:{...}}            estado autoritativo da partida
    {type:"chat", from, name, text}
    {type:"sys", text}                     mensagem do sistema
    {type:"queued"}                        você entrou na fila
    {type:"rating", profile:{...}}         seu perfil/rating no rank
    {type:"result", ...}                   resultado de partida valendo ELO
    {type:"error", message}
"""

import random
import threading

from game_session import Session, GameError
from ranking import RANKING

# Sem caracteres ambíguos (0/O, 1/I/L) — facilita ditar o código em voz alta.
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CODE_LEN = 4


def make_code(length=CODE_LEN):
    return "".join(random.choice(CODE_ALPHABET) for _ in range(length))


class Room:
    """Uma partida online: dois assentos (w/b), espectadores e o estado."""

    def __init__(self, code):
        self.code = code
        self.lock = threading.RLock()
        self.session = Session("medium", "w")  # ambas as cores são humanas
        self.seats = {"w": None, "b": None}
        self.names = {"w": None, "b": None}
        self.spectators = []
        self.rematch_votes = set()
        self.status = "waiting"  # waiting | playing
        self.started = False     # já teve os dois assentos ocupados?
        self.rated = False       # o resultado desta partida já foi gravado no rank?

    # ----------------------------- consultas -------------------------------
    def connections(self):
        out = [self.seats[c] for c in ("w", "b") if self.seats[c]]
        return out + list(self.spectators)

    def is_full(self):
        return self.seats["w"] is not None and self.seats["b"] is not None

    def is_empty(self):
        return not self.connections()

    def _name_of(self, color):
        if color == "w":
            return self.names["w"] or "Brancas"
        if color == "b":
            return self.names["b"] or "Pretas"
        return "Espectador"

    # ------------------------------ entrada --------------------------------
    def add(self, conn, name=None):
        with self.lock:
            if self.seats["w"] is None:
                color = "w"
            elif self.seats["b"] is None:
                color = "b"
            else:
                color = None  # vira espectador

            if color:
                conn.color = color
                self.seats[color] = conn
                self.names[color] = (name or ("Jogador 1" if color == "w" else "Jogador 2"))[:20]
            else:
                conn.color = None
                self.spectators.append(conn)
            conn.room = self

            if self.is_full() and self.status == "waiting":
                self.status = "playing"
                self.started = True

            self.broadcast_room()
            self.broadcast_state()
            if self.is_full():
                self._sys("Partida iniciada. Boa sorte!")
                self._send_ratings()
            return color

    def remove(self, conn):
        """Remove a conexão. Devolve True se a sala ficou vazia (pode ser apagada)."""
        with self.lock:
            left = None
            if conn.color and self.seats.get(conn.color) is conn:
                leaver = conn.color
                opponent = self.seats["b" if leaver == "w" else "w"]
                left = self._name_of(leaver)
                # Abandono de partida iniciada: o adversário vence por W.O.
                if (self.started and not self.session.game_over and not self.rated
                        and opponent is not None):
                    self._record("b" if leaver == "w" else "w", wo=True)
                self.seats[leaver] = None
                self.names[leaver] = None
                self.status = "waiting"
            elif conn in self.spectators:
                self.spectators.remove(conn)
            conn.room = None

            if left:
                self._sys("%s saiu da partida." % left)
            self.broadcast_room()
            if not self.is_empty():
                self.broadcast_state()
            return self.is_empty()

    # ------------------------------- lances --------------------------------
    def move(self, conn, move):
        with self.lock:
            if conn.color not in ("w", "b"):
                return conn.send_json({"type": "error", "message": "Você é espectador."})
            if not self.is_full() or self.status != "playing":
                return conn.send_json({"type": "error", "message": "Aguardando o adversário."})
            if self.session.game_over:
                return conn.send_json({"type": "error", "message": "A partida terminou."})
            if self.session.engine.turn != conn.color:
                return conn.send_json({"type": "error", "message": "Não é a sua vez."})
            if not isinstance(move, list) or len(move) != 4:
                return conn.send_json({"type": "error", "message": "Jogada inválida."})

            try:
                self.session.apply(move)
            except GameError as exc:
                return conn.send_json({"type": "error", "message": str(exc)})

            self.rematch_votes.clear()
            self.broadcast_state(self.session.last_anim)
            if self.session.game_over:
                self._record(self.session.winner or "draw")

    def undo_request(self, conn):
        # Não implementado de propósito: desfazer em partida online dá briga. ;)
        conn.send_json({"type": "error", "message": "Não dá para desfazer no multiplayer."})

    # -------------------------------- chat ---------------------------------
    def chat(self, conn, text):
        text = (text or "").strip()[:200]
        if not text:
            return
        with self.lock:
            name = self._name_of(conn.color) if conn.color else "Espectador"
            msg = {"type": "chat", "from": conn.color or "spec", "name": name, "text": text}
            for c in self.connections():
                c.send_json(msg)

    # ------------------------------ revanche -------------------------------
    def rematch(self, conn):
        with self.lock:
            if conn.color not in ("w", "b"):
                return conn.send_json({"type": "error", "message": "Só os jogadores podem pedir revanche."})
            if not self.session.game_over:
                return conn.send_json({"type": "error", "message": "A partida ainda está em andamento."})

            self.rematch_votes.add(conn.color)
            if self.rematch_votes == {"w", "b"}:
                # troca as cores e recomeça
                self.seats["w"], self.seats["b"] = self.seats["b"], self.seats["w"]
                self.names["w"], self.names["b"] = self.names["b"], self.names["w"]
                if self.seats["w"]:
                    self.seats["w"].color = "w"
                if self.seats["b"]:
                    self.seats["b"].color = "b"
                self.session = Session("medium", "w")
                self.rematch_votes.clear()
                self.status = "playing"
                self.started = True
                self.rated = False
                self.broadcast_room()
                self.broadcast_state()
                self._sys("Revanche! As cores foram trocadas.")
                self._send_ratings()
            else:
                self._sys("%s pediu revanche." % self._name_of(conn.color))

    # ------------------------------- ranking -------------------------------
    def _record(self, winner, wo=False):
        """Grava o resultado no rank mundial (no máximo uma vez por partida)."""
        if self.rated:
            return
        self.rated = True

        w_conn, b_conn = self.seats["w"], self.seats["b"]
        if not w_conn or not b_conn:
            return
        result = winner if winner in ("w", "b") else "draw"
        change = RANKING.record(getattr(w_conn, "pid", None),
                                getattr(b_conn, "pid", None), result)

        texto = {
            "w": "Brancas venceram",
            "b": "Pretas venceram",
            "draw": "Empate",
        }[result]
        if wo:
            texto += " (por desistência)"
        if change:
            texto += " — ELO atualizado."
        self._sys(texto)
        self._send_ratings(change=change)

    def _send_ratings(self, change=None):
        """Envia a cada jogador o seu perfil no rank; e um sinal de atualização."""
        for color in ("w", "b"):
            c = self.seats[color]
            if not c:
                continue
            pid = getattr(c, "pid", None)
            if not pid:
                continue
            prof = RANKING.get(pid)
            if not prof:
                continue
            msg = {"type": "rating", "profile": prof}
            if change:
                ch = change["white"] if color == "w" else change["black"]
                msg["delta"] = ch["delta"]
            c.send_json(msg)
        for c in self.connections():
            c.send_json({"type": "ranking_refresh"})

    # ---------------------------- transmissão ------------------------------
    def _sys(self, text):
        for c in self.connections():
            c.send_json({"type": "sys", "text": text})

    def _room_payload(self, conn):
        return {
            "type": "room",
            "code": self.code,
            "you": conn.color or "spec",
            "status": self.status,
            "names": {"w": self.names["w"], "b": self.names["b"]},
            "seated": {"w": self.seats["w"] is not None, "b": self.seats["b"] is not None},
            "spectators": len(self.spectators),
        }

    def broadcast_room(self):
        with self.lock:
            for c in self.connections():
                c.send_json(self._room_payload(c))

    def broadcast_state(self, anim=None):
        with self.lock:
            base = self.session.state(anim)
            for c in self.connections():
                st = dict(base)
                st["human_color"] = c.color or "spec"
                st["ai_color"] = None
                st["mode"] = "online"
                c.send_json({"type": "state", "state": st})


class Lobby:
    """Guarda todas as salas e a fila de pareamento aleatório."""

    def __init__(self):
        self.lock = threading.RLock()
        self.rooms = {}
        self.queue = []

    # ------------------------------- salas ---------------------------------
    def _new_room(self):
        code = make_code()
        while code in self.rooms:
            code = make_code()
        room = Room(code)
        self.rooms[code] = room
        return room

    def _drop(self, conn):
        """Tira a conexão da sala atual (assume lock)."""
        room = getattr(conn, "room", None)
        if not room:
            return
        empty = room.remove(conn)
        conn.room = None
        if empty:
            self.rooms.pop(room.code, None)

    # ------------------------------- eventos -------------------------------
    def handle(self, conn, msg):
        if not isinstance(msg, dict):
            return
        kind = msg.get("type")

        if kind == "create":
            return self._create(conn, msg)
        if kind == "join":
            return self._join(conn, msg)
        if kind == "queue":
            return self._enqueue(conn, msg)
        if kind == "leave":
            return self.disconnect(conn)

        room = getattr(conn, "room", None)
        if room is None:
            return conn.send_json({"type": "error", "message": "Você não está numa sala."})

        if kind == "move":
            room.move(conn, msg.get("move"))
        elif kind == "chat":
            room.chat(conn, msg.get("text"))
        elif kind == "rematch":
            room.rematch(conn)
        elif kind == "ping":
            conn.send_json({"type": "pong"})

    def _create(self, conn, msg):
        with self.lock:
            self._drop(conn)
            self._set_identity(conn, msg)
            room = self._new_room()
            conn.send_json({"type": "created", "code": room.code})
            room.add(conn, conn.name)

    def _join(self, conn, msg):
        code = str(msg.get("code", "")).strip().upper()
        with self.lock:
            room = self.rooms.get(code)
            if not room:
                return conn.send_json({"type": "error", "message": "Sala não encontrada."})
            self._drop(conn)
            self._set_identity(conn, msg)
            room.add(conn, conn.name)

    def _enqueue(self, conn, msg):
        with self.lock:
            self._drop(conn)
            self._set_identity(conn, msg)
            if conn in self.queue:
                return
            self.queue.append(conn)
            conn.send_json({"type": "queued"})
            if len(self.queue) >= 2:
                a = self.queue.pop(0)
                b = self.queue.pop(0)
                room = self._new_room()
                room.add(a, getattr(a, "name", None))
                room.add(b, getattr(b, "name", None))

    def _set_identity(self, conn, msg):
        """Atualiza apelido + id do jogador e devolve o perfil do rank."""
        raw = msg.get("name")
        name = str(raw).strip()[:20] if raw else ""
        conn.name = name or getattr(conn, "name", None)

        raw_pid = msg.get("pid")
        if raw_pid:
            pid = str(raw_pid).strip()[:64]
            if pid:
                conn.pid = pid

        pid = getattr(conn, "pid", None)
        if pid:
            prof = RANKING.upsert_player(pid, conn.name)
            if prof:
                conn.send_json({"type": "rating", "profile": prof})

    def disconnect(self, conn):
        with self.lock:
            if conn in self.queue:
                self.queue.remove(conn)
            self._drop(conn)

    # ------------------------------ diagnóstico ----------------------------
    def stats(self):
        with self.lock:
            return {"rooms": len(self.rooms), "queued": len(self.queue)}


# Instância única compartilhada pelos dois servidores.
LOBBY = Lobby()
