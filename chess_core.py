# -*- coding: utf-8 -*-
"""Nucleo puro do xadrez (sem pygame).

Engine de regras basicas + IA (negamax/alpha-beta) + notacao.
Compartilhado pelo jogo desktop (chess_ai.py) e pelo servidor web (server.py).
"""

import time
import random

# ---------------------------------------------------------------------------
# 4. ENGINE — REGRAS (movimentos básicos)
# ---------------------------------------------------------------------------
INITIAL = [
    ["bR", "bN", "bB", "bQ", "bK", "bB", "bN", "bR"],
    ["bP", "bP", "bP", "bP", "bP", "bP", "bP", "bP"],
    ["", "", "", "", "", "", "", ""],
    ["", "", "", "", "", "", "", ""],
    ["", "", "", "", "", "", "", ""],
    ["", "", "", "", "", "", "", ""],
    ["wP", "wP", "wP", "wP", "wP", "wP", "wP", "wP"],
    ["wR", "wN", "wB", "wQ", "wK", "wB", "wN", "wR"],
]

KNIGHT_OFF = ((-2, -1), (-2, 1), (-1, -2), (-1, 2), (1, -2), (1, 2), (2, -1), (2, 1))
KING_OFF   = ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1))
ROOK_DIR   = ((-1, 0), (1, 0), (0, -1), (0, 1))
BISHOP_DIR = ((-1, -1), (-1, 1), (1, -1), (1, 1))


def square_name(r, c):
    return "abcdefgh"[c] + str(8 - r)


def square_attacked(board, r, c, by):
    """A casa (r,c) está atacada por alguma peça de cor `by`?"""
    # Peões
    if by == "w":
        for dc in (-1, 1):
            rr, cc = r + 1, c + dc
            if 0 <= rr < 8 and 0 <= cc < 8 and board[rr][cc] == "wP":
                return True
    else:
        for dc in (-1, 1):
            rr, cc = r - 1, c + dc
            if 0 <= rr < 8 and 0 <= cc < 8 and board[rr][cc] == "bP":
                return True
    # Cavalos
    for dr, dc in KNIGHT_OFF:
        rr, cc = r + dr, c + dc
        if 0 <= rr < 8 and 0 <= cc < 8 and board[rr][cc] == by + "N":
            return True
    # Rei
    for dr, dc in KING_OFF:
        rr, cc = r + dr, c + dc
        if 0 <= rr < 8 and 0 <= cc < 8 and board[rr][cc] == by + "K":
            return True
    # Torre / Dama
    for dr, dc in ROOK_DIR:
        rr, cc = r + dr, c + dc
        while 0 <= rr < 8 and 0 <= cc < 8:
            p = board[rr][cc]
            if p:
                if p[0] == by and p[1] in ("R", "Q"):
                    return True
                break
            rr += dr
            cc += dc
    # Bispo / Dama
    for dr, dc in BISHOP_DIR:
        rr, cc = r + dr, c + dc
        while 0 <= rr < 8 and 0 <= cc < 8:
            p = board[rr][cc]
            if p:
                if p[0] == by and p[1] in ("B", "Q"):
                    return True
                break
            rr += dr
            cc += dc
    return False


class Engine:
    def __init__(self):
        self.reset()

    def reset(self):
        self.board = [row[:] for row in INITIAL]
        self.turn = "w"
        self.king_pos = {"w": (7, 4), "b": (0, 4)}

    def clone(self):
        e = Engine.__new__(Engine)
        e.board = [row[:] for row in self.board]
        e.turn = self.turn
        e.king_pos = dict(self.king_pos)
        return e

    # --- geração de jogadas -------------------------------------------------
    def generate_pseudo(self, color):
        b = self.board
        moves = []
        for r in range(8):
            for c in range(8):
                p = b[r][c]
                if not p or p[0] != color:
                    continue
                t = p[1]
                if t == "P":
                    d = -1 if color == "w" else 1
                    start = 6 if color == "w" else 1
                    nr = r + d
                    if 0 <= nr < 8 and not b[nr][c]:
                        moves.append((r, c, nr, c))
                        nr2 = r + 2 * d
                        if r == start and not b[nr2][c]:
                            moves.append((r, c, nr2, c))
                    for dc in (-1, 1):
                        nr, nc = r + d, c + dc
                        if 0 <= nr < 8 and 0 <= nc < 8:
                            q = b[nr][nc]
                            if q and q[0] != color:
                                moves.append((r, c, nr, nc))
                elif t == "N":
                    for dr, dc in KNIGHT_OFF:
                        nr, nc = r + dr, c + dc
                        if 0 <= nr < 8 and 0 <= nc < 8:
                            q = b[nr][nc]
                            if not q or q[0] != color:
                                moves.append((r, c, nr, nc))
                elif t == "K":
                    for dr, dc in KING_OFF:
                        nr, nc = r + dr, c + dc
                        if 0 <= nr < 8 and 0 <= nc < 8:
                            q = b[nr][nc]
                            if not q or q[0] != color:
                                moves.append((r, c, nr, nc))
                else:
                    dirs = ROOK_DIR if t == "R" else BISHOP_DIR if t == "B" else ROOK_DIR + BISHOP_DIR
                    for dr, dc in dirs:
                        nr, nc = r + dr, c + dc
                        while 0 <= nr < 8 and 0 <= nc < 8:
                            q = b[nr][nc]
                            if not q:
                                moves.append((r, c, nr, nc))
                            else:
                                if q[0] != color:
                                    moves.append((r, c, nr, nc))
                                break
                            nr += dr
                            nc += dc
        return moves

    def is_in_check(self, color):
        kr, kc = self.king_pos[color]
        return square_attacked(self.board, kr, kc, "b" if color == "w" else "w")

    def generate_legal(self, color):
        legal = []
        for m in self.generate_pseudo(color):
            undo = self.make_move(m)
            if not self.is_in_check(color):
                legal.append(m)
            self.unmake_move(m, undo)
        return legal

    # --- aplicar / desfazer -------------------------------------------------
    def make_move(self, move):
        fr, fc, tr, tc = move
        b = self.board
        piece = b[fr][fc]
        captured = b[tr][tc]
        b[tr][tc] = piece
        b[fr][fc] = ""
        promoted = False
        if piece[1] == "P" and ((piece[0] == "w" and tr == 0) or (piece[0] == "b" and tr == 7)):
            b[tr][tc] = piece[0] + "Q"
            promoted = True
        if piece[1] == "K":
            self.king_pos[piece[0]] = (tr, tc)
        self.turn = "b" if self.turn == "w" else "w"
        return (captured, promoted, piece)

    def unmake_move(self, move, undo):
        fr, fc, tr, tc = move
        captured, promoted, piece = undo
        b = self.board
        b[fr][fc] = piece
        b[tr][tc] = captured
        if piece[1] == "K":
            self.king_pos[piece[0]] = (fr, fc)
        self.turn = "b" if self.turn == "w" else "w"

    def legal_targets(self, r, c):
        return [(tr, tc) for (fr, fc, tr, tc) in self.generate_legal(self.board[r][c][0])
                if fr == r and fc == c]


def move_to_san(engine, move):
    """Notação algébrica simplificada (sem roque/en passant)."""
    fr, fc, tr, tc = move
    piece = engine.board[fr][fc]
    t = piece[1]
    dest = square_name(tr, tc)
    capture = engine.board[tr][tc] != ""

    if t == "P":
        san = ("abcdefgh"[fc] + "x" if capture else "") + dest
        if tr in (0, 7):
            san += "=Q"
    else:
        disamb = ""
        others = []
        for m in engine.generate_legal(piece[0]):
            ofr, ofc, otr, otc = m
            if (otr, otc) == (tr, tc) and (ofr, ofc) != (fr, fc):
                if engine.board[ofr][ofc][1] == t:
                    others.append((ofr, ofc))
        if others:
            same_file = any(oc == fc for _, oc in others)
            same_rank = any(or_ == fr for or_, _ in others)
            if not same_file:
                disamb = "abcdefgh"[fc]
            elif not same_rank:
                disamb = str(8 - fr)
            else:
                disamb = "abcdefgh"[fc] + str(8 - fr)
        san = t + disamb + ("x" if capture else "") + dest

    undo = engine.make_move(move)
    opp = engine.turn
    if engine.is_in_check(opp):
        san += "#" if not engine.generate_legal(opp) else "+"
    engine.unmake_move(move, undo)
    return san


# ---------------------------------------------------------------------------
# 5. IA — NEGAMAX + ALPHA-BETA + ITERATIVE DEEPENING
# ---------------------------------------------------------------------------
VAL = {"P": 100, "N": 320, "B": 330, "R": 500, "Q": 900, "K": 0}
MATE = 1_000_000
INF = 1_000_000_0

PST = {
    "P": [
        [0, 0, 0, 0, 0, 0, 0, 0],
        [50, 50, 50, 50, 50, 50, 50, 50],
        [10, 10, 20, 30, 30, 20, 10, 10],
        [5, 5, 10, 25, 25, 10, 5, 5],
        [0, 0, 0, 20, 20, 0, 0, 0],
        [5, -5, -10, 0, 0, -10, -5, 5],
        [5, 10, 10, -20, -20, 10, 10, 5],
        [0, 0, 0, 0, 0, 0, 0, 0],
    ],
    "N": [
        [-50, -40, -30, -30, -30, -30, -40, -50],
        [-40, -20, 0, 0, 0, 0, -20, -40],
        [-30, 0, 10, 15, 15, 10, 0, -30],
        [-30, 5, 15, 20, 20, 15, 5, -30],
        [-30, 0, 15, 20, 20, 15, 0, -30],
        [-30, 5, 10, 15, 15, 10, 5, -30],
        [-40, -20, 0, 5, 5, 0, -20, -40],
        [-50, -40, -30, -30, -30, -30, -40, -50],
    ],
    "B": [
        [-20, -10, -10, -10, -10, -10, -10, -20],
        [-10, 0, 0, 0, 0, 0, 0, -10],
        [-10, 0, 5, 10, 10, 5, 0, -10],
        [-10, 5, 5, 10, 10, 5, 5, -10],
        [-10, 0, 10, 10, 10, 10, 0, -10],
        [-10, 10, 10, 10, 10, 10, 10, -10],
        [-10, 5, 0, 0, 0, 0, 5, -10],
        [-20, -10, -10, -10, -10, -10, -10, -20],
    ],
    "R": [
        [0, 0, 0, 0, 0, 0, 0, 0],
        [5, 10, 10, 10, 10, 10, 10, 5],
        [-5, 0, 0, 0, 0, 0, 0, -5],
        [-5, 0, 0, 0, 0, 0, 0, -5],
        [-5, 0, 0, 0, 0, 0, 0, -5],
        [-5, 0, 0, 0, 0, 0, 0, -5],
        [-5, 0, 0, 0, 0, 0, 0, -5],
        [0, 0, 0, 5, 5, 0, 0, 0],
    ],
    "Q": [
        [-20, -10, -10, -5, -5, -10, -10, -20],
        [-10, 0, 0, 0, 0, 0, 0, -10],
        [-10, 0, 5, 5, 5, 5, 0, -10],
        [-5, 0, 5, 5, 5, 5, 0, -5],
        [0, 0, 5, 5, 5, 5, 0, -5],
        [-10, 5, 5, 5, 5, 5, 0, -10],
        [-10, 0, 5, 0, 0, 0, 0, -10],
        [-20, -10, -10, -5, -5, -10, -10, -20],
    ],
    "K": [
        [-30, -40, -40, -50, -50, -40, -40, -30],
        [-30, -40, -40, -50, -50, -40, -40, -30],
        [-30, -40, -40, -50, -50, -40, -40, -30],
        [-30, -40, -40, -50, -50, -40, -40, -30],
        [-20, -30, -30, -40, -40, -30, -30, -20],
        [-10, -20, -20, -20, -20, -20, -20, -10],
        [20, 20, 0, 0, 0, 0, 20, 20],
        [20, 30, 10, 0, 0, 10, 30, 20],
    ],
}


def evaluate(engine):
    """Pontuação do ponto de vista das brancas (positivo = brancas melhor)."""
    b = engine.board
    score = 0
    for r in range(8):
        for c in range(8):
            p = b[r][c]
            if not p:
                continue
            t = p[1]
            v = VAL[t] + PST[t][r][c]
            if p[0] == "w":
                score += v
            else:
                score -= v
    return score


class _Timeout(Exception):
    pass


class AI:
    def __init__(self, level="medium"):
        self.nodes = 0
        self.set_level(level)

    def set_level(self, level):
        self.level = level
        if level == "easy":
            self.depth, self.rand, self.budget, self.quiesce = 1, 0.55, 0.25, False
        elif level == "medium":
            self.depth, self.rand, self.budget, self.quiesce = 3, 0.06, 0.9, True
        else:
            self.depth, self.rand, self.budget, self.quiesce = 4, 0.0, 2.4, True

    # --- utilitários --------------------------------------------------------
    def _deadline_hit(self):
        return time.time() > self._deadline

    def _order(self, engine, moves):
        b = engine.board

        def key(m):
            fr, fc, tr, tc = m
            victim = b[tr][tc]
            if victim:
                return -(VAL[victim[1]] * 10 - VAL[b[fr][fc][1]])
            return 0

        return sorted(moves, key=key)

    # --- busca --------------------------------------------------------------
    def _quiesce(self, engine, alpha, beta, qdepth):
        if self._deadline_hit():
            raise _Timeout()
        self.nodes += 1
        sign = 1 if engine.turn == "w" else -1
        stand = sign * evaluate(engine)
        if stand >= beta:
            return beta
        if stand > alpha:
            alpha = stand
        if qdepth >= 4:
            return alpha
        caps = [m for m in engine.generate_legal(engine.turn)
                if engine.board[m[2]][m[3]] != ""]
        caps = self._order(engine, caps)
        for m in caps:
            undo = engine.make_move(m)
            score = -self._quiesce(engine, -beta, -alpha, qdepth + 1)
            engine.unmake_move(m, undo)
            if score >= beta:
                return beta
            if score > alpha:
                alpha = score
        return alpha

    def _negamax(self, engine, depth, alpha, beta, ply):
        if self._deadline_hit():
            raise _Timeout()
        self.nodes += 1
        sign = 1 if engine.turn == "w" else -1
        moves = engine.generate_legal(engine.turn)
        if not moves:
            if engine.is_in_check(engine.turn):
                return -(MATE - ply)
            return 0
        if depth == 0:
            if self.quiesce:
                return self._quiesce(engine, alpha, beta, 0)
            return sign * evaluate(engine)

        best = -INF
        for m in self._order(engine, moves):
            undo = engine.make_move(m)
            score = -self._negamax(engine, depth - 1, -beta, -alpha, ply + 1)
            engine.unmake_move(m, undo)
            if score > best:
                best = score
            if score > alpha:
                alpha = score
            if alpha >= beta:
                break
        return best

    def _root(self, engine, depth):
        moves = engine.generate_legal(engine.turn)
        moves = self._order(engine, moves)
        if self.rand:
            random.shuffle(moves)
            moves = self._order(engine, moves)
        best_move, alpha, best = None, -INF, -INF
        for m in moves:
            undo = engine.make_move(m)
            score = -self._negamax(engine, depth - 1, -INF, -alpha, 1)
            engine.unmake_move(m, undo)
            if score > best:
                best, best_move = score, m
            if score > alpha:
                alpha = score
        return best, best_move

    def choose_move(self, engine):
        legal = engine.generate_legal(engine.turn)
        if not legal:
            return None
        if random.random() < self.rand:
            return random.choice(legal)

        self.nodes = 0
        self._deadline = time.time() + self.budget
        best, best_move = None, None
        for depth in range(1, self.depth + 1):
            try:
                score, mv = self._root(engine, depth)
            except _Timeout:
                break
            if mv is not None:
                best, best_move = score, mv
            if abs(score) > MATE - 1000:
                break
        return best_move if best_move else random.choice(legal)


