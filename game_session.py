# -*- coding: utf-8 -*-
"""
Sessão de partida do xadrez — Python puro, sem framework e sem pygame.

Usada tanto pelo servidor FastAPI (server.py) quanto pelo servidor
sem dependências (server_stdlib.py). Não importa nada além de chess_core.
"""

from chess_core import Engine, AI, move_to_san

LEVELS = {"easy", "medium", "hard"}


class GameError(Exception):
    """Erro de regra/jogada. Cada servidor traduz para o status HTTP adequado."""


class Session:
    def __init__(self, level: str = "medium", human_color: str = "w"):
        self.engine = Engine()
        self.level = level if level in LEVELS else "medium"
        self.human_color = human_color if human_color in ("w", "b") else "w"
        self.ai_color = "b" if self.human_color == "w" else "w"
        self.history: list[dict] = []
        self.captured: dict[str, list] = {"w": [], "b": []}
        self.game_over = False
        self.result = ""
        self.winner = None
        self.last_move = None
        self.last_anim = None

    # --- jogadas ------------------------------------------------------------
    def apply(self, move):
        fr, fc, tr, tc = move
        piece = self.engine.board[fr][fc]
        if not piece or piece[0] != self.engine.turn:
            raise GameError("Peça inválida para o turno atual")
        if tuple(move) not in self.engine.generate_legal(self.engine.turn):
            raise GameError("Jogada ilegal")

        captured = self.engine.board[tr][tc]
        san = move_to_san(self.engine, move)
        side = self.engine.turn
        undo = self.engine.make_move(move)
        self.history.append({"move": move, "undo": undo, "san": san,
                             "captured": captured, "side": side})
        if captured:
            self.captured[side].append(captured)
        self.last_move = move
        # "piece" é a peça ANTES do lance (promoção anima o peão chegando).
        self.last_anim = {
            "piece": piece,
            "from": [fr, fc], "to": [tr, tc],
            "captured": captured or None,
        }
        self._check_end()
        return san

    def ai_move(self):
        if self.game_over or self.engine.turn != self.ai_color:
            return None
        mv = AI(self.level).choose_move(self.engine)
        if not mv:
            return None
        self.apply(list(mv))
        return list(mv)

    def undo(self):
        while self.history:
            rec = self.history.pop()
            self.engine.unmake_move(rec["move"], rec["undo"])
            if rec["captured"]:
                lst = self.captured[rec["side"]]
                if rec["captured"] in lst:
                    lst.remove(rec["captured"])
            if self.engine.turn == self.human_color:
                break
        self.game_over = False
        self.result = ""
        self.winner = None
        self.last_move = None
        self.last_anim = None

    def _check_end(self):
        color = self.engine.turn
        if not self.engine.generate_legal(color):
            self.game_over = True
            if self.engine.is_in_check(color):
                self.winner = "b" if color == "w" else "w"
                nome = "Brancas" if self.winner == "w" else "Pretas"
                self.result = f"Xeque-mate — {nome} vencem"
            else:
                self.result = "Empate por afogamento"

    # --- serialização -------------------------------------------------------
    def state(self, anim=None):
        turn = self.engine.turn
        check = (not self.game_over) and self.engine.is_in_check(turn)
        check_sq = list(self.engine.king_pos[turn]) if check else None
        return {
            "board": [row[:] for row in self.engine.board],
            "turn": turn,
            "human_color": self.human_color,
            "ai_color": self.ai_color,
            "level": self.level,
            "legal": [list(m) for m in (
                self.engine.generate_legal(turn) if not self.game_over else [])],
            "last_move": list(self.last_move) if self.last_move else None,
            "history": [{"san": r["san"], "side": r["side"]} for r in self.history],
            "captured": {k: list(v) for k, v in self.captured.items()},
            "game_over": self.game_over,
            "result": self.result,
            "winner": self.winner,
            "check": check,
            "check_square": check_sq,
            "anim": anim,
        }
