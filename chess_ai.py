# -*- coding: utf-8 -*-
"""
XADREZ — Edição de Clube
Direção de arte: objeto de biblioteca/torneio. Papel, madeira, latão.
Camadas:
    - Engine   : regras básicas (movimentos, captura, promoção a dama, xeque, mate, afogamento)
    - AI       : negamax com alpha-beta, iterative deepening e quiescence (3 níveis)
    - Render/UI: tokens, moldura, HUD "livro de escore"
    - App      : loop principal

Regras: básicas (SEM roque e SEM en passant), conforme escolha do projeto.
"""

import sys
import math
import time
import random
import threading

import pygame

# ---------------------------------------------------------------------------
# 1. TOKENS DE DESIGN
# ---------------------------------------------------------------------------
class C:
    # Fundo e superfícies
    PAPER      = (237, 230, 214)   # fundo geral (papel)
    PAPER_DIM  = (224, 214, 194)   # superfície de botões inativos
    PAPER_HI   = (246, 241, 229)   # hover
    RULE       = (198, 182, 152)   # réguas finas

    # Tinta / texto
    INK        = (28, 25, 20)
    INK_SOFT   = (92, 84, 70)

    # Tabuleiro
    FRAME      = (74, 56, 40)      # moldura de madeira
    FRAME_EDGE = (52, 39, 27)
    BOARD_L    = (233, 222, 198)   # casa clara
    BOARD_D    = (124, 94, 64)     # casa escura

    # Acentos
    BRASS      = (176, 141, 87)    # latão (ativo/destaque)
    BRASS_D    = (140, 110, 66)
    BLOOD      = (150, 44, 38)     # xeque / perigo
    GOOD       = (74, 110, 86)     # jogadas legais

    # Realces translúcidos (RGBA)
    LAST_HL    = (214, 176, 104, 78)
    SEL_HL     = (245, 222, 150, 130)


# ---------------------------------------------------------------------------
# 2. GEOMETRIA / LAYOUT
# ---------------------------------------------------------------------------
N          = 8
SQUARE     = 72
BOARD_PX   = SQUARE * N          # 576
FRAME      = 26                  # espessura da moldura de madeira
BOARD_BLOCK = BOARD_PX + 2 * FRAME

PAD        = 28
HEADER_H   = 78
PANEL_W    = 344

WIDTH  = PAD * 3 + BOARD_BLOCK + PANEL_W
HEIGHT = HEADER_H + PAD + BOARD_BLOCK + PAD

BOARD_X = PAD + FRAME
BOARD_Y = HEADER_H + PAD + FRAME

PANEL_X = PAD + BOARD_BLOCK + PAD
PANEL_Y = HEADER_H + PAD
PANEL_H = BOARD_BLOCK

FPS = 60
MIN_AI_DELAY = 0.35
ANIM_DUR = 0.18      # deslize da peça (curto: não atrasa a partida)


# ---------------------------------------------------------------------------
# 3. HELPERS DE DESENHO
# ---------------------------------------------------------------------------
def make_font(names, size, bold=False, italic=False):
    """Tenta uma lista de fontes do sistema e usa a primeira disponível."""
    return pygame.font.SysFont(",".join(names), size, bold=bold, italic=italic)


def text_blit(surf, text, font, color, pos, anchor="topleft"):
    img = font.render(text, True, color)
    rect = img.get_rect(**{anchor: pos})
    surf.blit(img, rect)
    return rect


def text_spaced(surf, text, font, color, pos, spacing=2, anchor="topleft"):
    """Texto com espaçamento entre letras (aspecto editorial para rótulos)."""
    widths = [font.size(ch)[0] for ch in text]
    total = sum(widths) + spacing * max(0, len(text) - 1)
    x, y = pos
    if anchor in ("center", "topright"):
        x -= total // 2
    elif anchor in ("midright", "right"):
        x -= total
    for ch, w in zip(text, widths):
        surf.blit(font.render(ch, True, color), (x, y))
        x += w + spacing
    return total


def hline(surf, x1, x2, y, color=C.RULE, width=1):
    pygame.draw.line(surf, color, (x1, y), (x2, y), width)


# ---------------------------------------------------------------------------
# 4-5. NUCLEO (regras + IA + notacao) — modulo compartilhado
# ---------------------------------------------------------------------------
from chess_core import (  # noqa: E402
    INITIAL, Engine, AI, move_to_san, square_name, square_attacked,
    evaluate, VAL, MATE, INF, PST,
    KNIGHT_OFF, KING_OFF, ROOK_DIR, BISHOP_DIR, _Timeout,
)

# ---------------------------------------------------------------------------
# 6. UI — COMPONENTES
# ---------------------------------------------------------------------------
class Button:
    def __init__(self, rect, label):
        self.rect = pygame.Rect(rect)
        self.label = label

    def hovered(self):
        return self.rect.collidepoint(pygame.mouse.get_pos())


def draw_button(surf, rect, label, font, active=False, danger=False):
    hover = rect.collidepoint(pygame.mouse.get_pos())
    if active:
        fill, border, txt = C.BRASS, C.BRASS_D, C.INK
    elif hover:
        fill, border, txt = C.PAPER_HI, C.BRASS, C.INK
    else:
        fill, border, txt = C.PAPER_DIM, C.RULE, C.INK_SOFT
    if danger and hover:
        border = C.BLOOD
        txt = C.BLOOD
    pygame.draw.rect(surf, fill, rect)
    pygame.draw.rect(surf, border, rect, 2)
    text_blit(surf, label, font, txt, rect.center, "center")


# ---------------------------------------------------------------------------
# 7. APP
# ---------------------------------------------------------------------------
LEVELS = [("easy", "FÁCIL"), ("medium", "MÉDIO"), ("hard", "DIFÍCIL")]


class App:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("Xadrez — Edição de Clube")
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        self.clock = pygame.time.Clock()

        # Fontes
        serif = ["georgia", "palatino linotype", "book antiqua", "cambria",
                 "times new roman", "dejavuserif", "serif"]
        sans = ["segoe ui", "calibri", "candara", "helvetica neue",
                "arial", "dejavusans", "sans"]
        mono = ["consolas", "cascadia mono", "courier new", "dejavusansmono", "monospace"]
        sym = ["segoeuisymbol", "dejavusans", "freeserif", "notosanssymbols2",
               "notosanssymbols", "symbola", "arialunicodems"]

        self.f_title = make_font(serif, 30, bold=True)
        self.f_sub = make_font(sans, 12)
        self.f_label = make_font(sans, 13, bold=True)
        self.f_body = make_font(sans, 16)
        self.f_bodyb = make_font(sans, 16, bold=True)
        self.f_small = make_font(sans, 13)
        self.f_move = make_font(mono, 14)
        self.f_chip = make_font(sans, 15, bold=True)
        self.f_over = make_font(serif, 30, bold=True)
        self.f_over2 = make_font(sans, 15)
        self.f_coord = make_font(sans, 12, bold=True)
        self.f_piece = make_font(sym, 58)

        # Estado de jogo
        self.engine = Engine()
        self.human_color = "w"
        self.ai_color = "b"
        self.level = "medium"
        self.selected = None
        self.targets = []
        self.last_move = None
        self.history = []
        self.captured = {"w": [], "b": []}
        self.game_over = False
        self.result = ""
        self.winner = None

        # Estado da IA (thread)
        self.thinking = False
        self.ai_result = None
        self.ai_gen = 0
        self.ai_start = 0.0

        # Estado da animação de movimento
        self.anim = None
        self.pending_finish = False

        self._piece_cache = {}
        self._layout()
        self._build_buttons()

    # --- layout -------------------------------------------------------------
    def _layout(self):
        ix = PANEL_X + 22
        iw = PANEL_W - 44
        y = PANEL_Y + 18

        self.lbl_level_y = y
        y += 24
        bw = (iw - 18) // 3
        self.level_rects = {}
        for i, (key, _) in enumerate(LEVELS):
            self.level_rects[key] = pygame.Rect(ix + i * (bw + 9), y, bw, 38)
        y += 38 + 20

        self.turn_card = pygame.Rect(ix, y, iw, 60)
        y += 60 + 20

        self.lbl_moves_y = y
        y += 24
        self.moves_rect = pygame.Rect(ix, y, iw, 208)
        y += 208 + 20

        self.lbl_cap_y = y
        y += 24
        self.cap_rect = pygame.Rect(ix, y, iw, 86)
        y += 86 + 18

        half = (iw - 12) // 2
        self.rect_new = pygame.Rect(ix, y, half, 42)
        self.rect_undo = pygame.Rect(ix + half + 12, y, half, 42)

    def _build_buttons(self):
        self.btn_new = Button(self.rect_new, "NOVO JOGO")
        self.btn_undo = Button(self.rect_undo, "DESFAZER")

    # --- fluxo de jogo ------------------------------------------------------
    def new_game(self):
        self.ai_gen += 1
        self.engine.reset()
        self.selected = None
        self.targets = []
        self.last_move = None
        self.history = []
        self.captured = {"w": [], "b": []}
        self.game_over = False
        self.result = ""
        self.winner = None
        self.thinking = False
        self.ai_result = None
        self.anim = None
        self.pending_finish = False
        if self.engine.turn == self.ai_color:
            self._start_ai()

    def _start_ai(self):
        if self.game_over:
            return
        self.thinking = True
        self.ai_gen += 1
        gen = self.ai_gen
        self.ai_start = time.time()
        self.ai_result = None
        clone = self.engine.clone()
        level = self.level

        def work():
            try:
                mv = AI(level).choose_move(clone)
            except Exception:
                mv = None
            self.ai_result = (gen, mv)

        threading.Thread(target=work, daemon=True).start()

    def _pump_ai(self):
        if self.anim or not self.thinking or self.ai_result is None:
            return
        gen, mv = self.ai_result
        if gen != self.ai_gen:
            return
        if time.time() - self.ai_start < MIN_AI_DELAY:
            return
        self.thinking = False
        self.ai_result = None
        if mv:
            self.apply_move(mv)

    def apply_move(self, move):
        fr, fc, tr, tc = move
        piece = self.engine.board[fr][fc]
        captured = self.engine.board[tr][tc]
        san = move_to_san(self.engine, move)
        side = self.engine.turn
        undo = self.engine.make_move(move)
        self.history.append({"move": move, "undo": undo, "san": san,
                             "captured": captured, "side": side})
        if captured:
            self.captured[side].append(captured)
        self.selected = None
        self.targets = []
        self.last_move = move
        # A conclusão (xeque / vez da IA) só ocorre quando a peça assenta
        self._begin_anim(piece, move, captured)

    def _begin_anim(self, piece, move, captured):
        fr, fc, tr, tc = move
        self.anim = {
            "piece": piece, "fr": fr, "fc": fc, "tr": tr, "tc": tc,
            "t0": time.time(), "dur": ANIM_DUR,
            "captured": captured,
        }
        self.pending_finish = True

    def _update_anim(self):
        if not self.anim:
            return
        if time.time() - self.anim["t0"] >= self.anim["dur"]:
            self.anim = None
            if self.pending_finish:
                self.pending_finish = False
                self._finish_move()

    def _finish_move(self):
        self._check_end()
        if not self.game_over and self.engine.turn == self.ai_color:
            self._start_ai()

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

    def undo(self):
        if self.thinking or not self.history:
            return
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
        self.selected = None
        self.targets = []
        self.last_move = None
        self.anim = None
        self.pending_finish = False
        # Se, após desfazer, o turno ficou com a IA, ela deve jogar de novo
        if self.engine.turn == self.ai_color:
            self._start_ai()

    # --- interação ----------------------------------------------------------
    def on_click(self, pos):
        # Controles sempre acessíveis (inclusive com a partida encerrada)
        for key, rect in self.level_rects.items():
            if rect.collidepoint(pos):
                self.level = key
                return
        if self.rect_new.collidepoint(pos):
            self.new_game()
            return
        if self.rect_undo.collidepoint(pos):
            self.undo()
            return
        if self.game_over or self.anim:
            return
        if self.thinking or self.engine.turn != self.human_color:
            return
        if not (BOARD_X <= pos[0] < BOARD_X + BOARD_PX and
                BOARD_Y <= pos[1] < BOARD_Y + BOARD_PX):
            return
        col = (pos[0] - BOARD_X) // SQUARE
        row = (pos[1] - BOARD_Y) // SQUARE
        piece = self.engine.board[row][col]

        if self.selected is None:
            if piece and piece[0] == self.human_color:
                self.selected = (row, col)
                self.targets = self.engine.legal_targets(row, col)
        else:
            if (row, col) in self.targets:
                self.apply_move((self.selected[0], self.selected[1], row, col))
                self.selected = None
                self.targets = []
            elif piece and piece[0] == self.human_color:
                self.selected = (row, col)
                self.targets = self.engine.legal_targets(row, col)
            else:
                self.selected = None
                self.targets = []

    # --- peças --------------------------------------------------------------
    def piece_surface(self, code):
        key = code
        if key in self._piece_cache:
            return self._piece_cache[key]
        glyph = {"K": "\u265A", "Q": "\u265B", "R": "\u265C",
                 "B": "\u265D", "N": "\u265E", "P": "\u265F"}[code[1]]
        if code[0] == "w":
            fill, outline = (245, 239, 224), (40, 34, 26)
        else:
            fill, outline = (34, 30, 24), (222, 212, 188)
        base = self.f_piece.render(glyph, True, fill)
        ol = self.f_piece.render(glyph, True, outline)
        w, h = base.get_size()
        surf = pygame.Surface((w + 4, h + 4), pygame.SRCALPHA)
        for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2),
                       (-1, -1), (1, -1), (-1, 1), (1, 1)):
            surf.blit(ol, (dx + 2, dy + 2))
        surf.blit(base, (2, 2))
        self._piece_cache[key] = surf
        return surf

    # --- render -------------------------------------------------------------
    def draw(self):
        s = self.screen
        s.fill(C.PAPER)
        self.draw_header()
        self.draw_board()
        self.draw_panel()

    def draw_header(self):
        s = self.screen
        text_blit(s, "XADREZ", self.f_title, C.INK, (PAD, 13))
        text_spaced(s, "EDIÇÃO DE CLUBE", self.f_sub, C.INK_SOFT, (PAD + 3, 56), 3)
        hline(s, PAD, WIDTH - PAD, HEADER_H - 1, C.BRASS, 2)
        hline(s, PAD, WIDTH - PAD, HEADER_H + 1, C.RULE, 1)

        # Chip de status (direita)
        if self.game_over:
            txt, accent = self.result, C.BLOOD if self.winner else C.INK_SOFT
        elif self.thinking:
            dots = "." * (1 + int((time.time() * 3) % 3))
            txt, accent = f"IA pensando{dots}", C.BRASS_D
        elif self.engine.turn == "w":
            txt, accent = "Vez das Brancas", C.INK
        else:
            txt, accent = "Vez das Pretas", C.INK

        right = WIDTH - PAD
        text_blit(s, txt, self.f_chip, accent, (right, 30), "midright")
        # swatch de cor da vez
        sw = pygame.Rect(right - self.f_chip.size(txt)[0] - 30, 22, 16, 16)
        if not self.game_over and not self.thinking:
            swatch_col = (245, 239, 224) if self.engine.turn == "w" else (34, 30, 24)
            pygame.draw.rect(s, swatch_col, sw)
            pygame.draw.rect(s, C.INK_SOFT, sw, 1)

    def draw_board(self):
        s = self.screen
        # moldura de madeira + bisel
        frame = pygame.Rect(PAD, HEADER_H + PAD, BOARD_BLOCK, BOARD_BLOCK)
        pygame.draw.rect(s, C.FRAME, frame)
        pygame.draw.rect(s, C.FRAME_EDGE, frame, 3)
        pygame.draw.rect(s, C.BRASS, frame.inflate(-2 * FRAME + 4, -2 * FRAME + 4), 1)

        in_check = {"w": False, "b": False}
        for col_ in ("w", "b"):
            kr, kc = self.engine.king_pos[col_]
            in_check[col_] = self.engine.is_in_check(col_)

        for r in range(8):
            for c in range(8):
                x = BOARD_X + c * SQUARE
                y = BOARD_Y + r * SQUARE
                base = C.BOARD_L if (r + c) % 2 == 0 else C.BOARD_D
                pygame.draw.rect(s, base, (x, y, SQUARE, SQUARE))

                # Realce da última jogada
                if self.last_move:
                    fr, fc, tr, tc = self.last_move
                    if (r, c) in ((fr, fc), (tr, tc)):
                        ov = pygame.Surface((SQUARE, SQUARE), pygame.SRCALPHA)
                        ov.fill(C.LAST_HL)
                        s.blit(ov, (x, y))

                # Casa selecionada
                if self.selected == (r, c):
                    ov = pygame.Surface((SQUARE, SQUARE), pygame.SRCALPHA)
                    ov.fill(C.SEL_HL)
                    s.blit(ov, (x, y))
                    pygame.draw.rect(s, C.BRASS_D, (x + 1, y + 1, SQUARE - 2, SQUARE - 2), 2)

                # Rei em xeque
                p = self.engine.board[r][c]
                if p and p[1] == "K" and in_check[p[0]]:
                    ov = pygame.Surface((SQUARE, SQUARE), pygame.SRCALPHA)
                    a = 150 + int(60 * (0.5 + 0.5 * abs((time.time() * 2) % 2 - 1)))
                    ov.fill((C.BLOOD[0], C.BLOOD[1], C.BLOOD[2], a))
                    s.blit(ov, (x, y))

        # Alvos legais (forma, não só cor)
        for (tr, tc) in self.targets:
            cx = BOARD_X + tc * SQUARE + SQUARE // 2
            cy = BOARD_Y + tr * SQUARE + SQUARE // 2
            if self.engine.board[tr][tc]:
                pygame.draw.circle(s, C.GOOD, (cx, cy), SQUARE // 2 - 6, 4)
            else:
                pygame.draw.circle(s, C.GOOD, (cx, cy), 9)

        # Peças (a peça em movimento é desenhada separadamente)
        anim = self.anim
        for r in range(8):
            for c in range(8):
                p = self.engine.board[r][c]
                if not p:
                    continue
                if anim and (r, c) == (anim["tr"], anim["tc"]):
                    continue
                surf = self.piece_surface(p)
                rect = surf.get_rect(center=(BOARD_X + c * SQUARE + SQUARE // 2,
                                             BOARD_Y + r * SQUARE + SQUARE // 2))
                s.blit(surf, rect)

        # Animação de movimento: peça erguida + sombra de contato + captura
        if anim:
            prog = min(1.0, (time.time() - anim["t0"]) / anim["dur"])
            ease = 1 - (1 - prog) ** 3           # ease-out cubic
            x0 = BOARD_X + anim["fc"] * SQUARE + SQUARE // 2
            y0 = BOARD_Y + anim["fr"] * SQUARE + SQUARE // 2
            x1 = BOARD_X + anim["tc"] * SQUARE + SQUARE // 2
            y1 = BOARD_Y + anim["tr"] * SQUARE + SQUARE // 2
            cx = x0 + (x1 - x0) * ease
            cy = y0 + (y1 - y0) * ease
            lift = 9 * math.sin(math.pi * prog)  # erguer suave no meio do trajeto

            # Sombra de contato (encolhe conforme a peça sobe)
            sh_w = SQUARE * (0.46 - 0.14 * (lift / 9.0))
            sh = pygame.Surface((SQUARE, SQUARE), pygame.SRCALPHA)
            pygame.draw.ellipse(sh, (0, 0, 0, 55),
                                (int(SQUARE / 2 - sh_w / 2), int(SQUARE * 0.66),
                                 int(sh_w), int(SQUARE * 0.15)))
            s.blit(sh, (int(cx - SQUARE / 2), int(cy - SQUARE / 2)))

            # Peça capturada: desvanece no primeiro trecho
            if anim["captured"]:
                cs = self.piece_surface(anim["captured"]).copy()
                alpha = max(0, int(255 * (1 - min(1.0, prog / 0.55))))
                cs.set_alpha(alpha)
                s.blit(cs, cs.get_rect(center=(int(x1), int(y1))))

            surf = self.piece_surface(anim["piece"])
            s.blit(surf, surf.get_rect(center=(int(cx), int(cy - lift))))

        # Coordenadas
        for c in range(8):
            x = BOARD_X + c * SQUARE + SQUARE // 2
            text_blit(s, "abcdefgh"[c], self.f_coord, C.BRASS,
                      (x, BOARD_Y + BOARD_PX + FRAME // 2), "center")
        for r in range(8):
            y = BOARD_Y + r * SQUARE + SQUARE // 2
            text_blit(s, str(8 - r), self.f_coord, C.BRASS,
                      (BOARD_X - FRAME // 2, y), "center")

    def draw_panel(self):
        s = self.screen
        # Rótulo: OPONENTE
        text_spaced(s, "OPONENTE", self.f_label, C.BRASS_D, (PANEL_X + 22, self.lbl_level_y), 2)
        for key, label in LEVELS:
            draw_button(s, self.level_rects[key], label, self.f_bodyb,
                        active=(self.level == key))

        # Cartão: vez
        card = self.turn_card
        pygame.draw.rect(s, C.PAPER_DIM, card)
        pygame.draw.rect(s, C.RULE, card, 1)
        pygame.draw.rect(s, C.BRASS, (card.x, card.y, 4, card.height))
        if self.game_over:
            txt, sub = "PARTIDA ENCERRADA", self.result
        elif self.thinking:
            txt, sub = "IA PENSANDO", "avaliando posições…"
        elif self.engine.turn == "w":
            txt, sub = "VEZ DAS BRANCAS", "seu lance" if self.human_color == "w" else "lance da IA"
        else:
            txt, sub = "VEZ DAS PRETAS", "seu lance" if self.human_color == "b" else "lance da IA"
        text_blit(s, txt, self.f_bodyb, C.INK, (card.x + 16, card.y + 12))
        text_blit(s, sub, self.f_small, C.INK_SOFT, (card.x + 16, card.y + 34))

        # Lances
        text_spaced(s, "NOTAÇÃO", self.f_label, C.BRASS_D, (PANEL_X + 22, self.lbl_moves_y), 2)
        mr = self.moves_rect
        hline(s, mr.x, mr.right, mr.y, C.RULE, 1)
        rows = 8
        row_h = 24
        # cabeçalho de colunas
        col_b = mr.x + 130
        col_n = mr.x + 224
        text_blit(s, "Nº", self.f_small, C.INK_SOFT, (mr.x + 2, mr.y + 6))
        text_blit(s, "BRANCAS", self.f_small, C.INK_SOFT, (col_b, mr.y + 6))
        text_blit(s, "PRETAS", self.f_small, C.INK_SOFT, (col_n, mr.y + 6))
        hline(s, mr.x, mr.right, mr.y + 26, C.RULE, 1)

        start = max(0, (len(self.history) + 1) // 2 - rows)
        yy = mr.y + 32
        for i in range(start, (len(self.history) + 1) // 2):
            n = i + 1
            wm = self.history[2 * i]["san"]
            bm = self.history[2 * i + 1]["san"] if 2 * i + 1 < len(self.history) else ""
            is_last = (2 * i + 1 >= len(self.history) - 1)
            col = C.INK if is_last else C.INK_SOFT
            text_blit(s, f"{n}.", self.f_move, C.INK_SOFT, (mr.x + 2, yy))
            text_blit(s, wm, self.f_move, col, (col_b, yy))
            text_blit(s, bm, self.f_move, col, (col_n, yy))
            yy += row_h
        hline(s, mr.x, mr.right, mr.bottom, C.RULE, 1)

        # Capturadas
        text_spaced(s, "CAPTURADAS", self.f_label, C.BRASS_D,
                    (PANEL_X + 22, self.lbl_cap_y), 2)
        cr = self.cap_rect
        self._draw_captured_row(cr.x, cr.y, "w")
        self._draw_captured_row(cr.x, cr.y + 42, "b")

        # Botões
        draw_button(s, self.rect_new, "NOVO JOGO", self.f_bodyb)
        draw_button(s, self.rect_undo, "DESFAZER", self.f_bodyb,
                    danger=(not self.history))

        # Overlay de fim de jogo sobre o tabuleiro
        if self.game_over:
            area = pygame.Rect(PAD, HEADER_H + PAD, BOARD_BLOCK, BOARD_BLOCK)
            ov = pygame.Surface(area.size, pygame.SRCALPHA)
            ov.fill((20, 17, 13, 190))
            s.blit(ov, area.topleft)
            box = pygame.Rect(0, 0, 380, 130)
            box.center = area.center
            pygame.draw.rect(s, C.PAPER, box)
            pygame.draw.rect(s, C.BRASS, box, 3)
            text_blit(s, "FIM DE PARTIDA", self.f_small, C.BRASS_D,
                      (box.centerx, box.y + 20), "center")
            text_blit(s, self.result, self.f_over, C.INK,
                      (box.centerx, box.y + 58), "center")
            text_blit(s, "N para novo jogo", self.f_over2, C.INK_SOFT,
                      (box.centerx, box.y + 100), "center")

    def _draw_captured_row(self, x, y, side):
        s = self.screen
        label = "BRANCAS" if side == "w" else "PRETAS"
        text_blit(s, label, self.f_small, C.INK_SOFT, (x, y + 8))
        px = x + 72
        avail = self.cap_rect.right - px
        pieces = sorted(self.captured[side], key=lambda p: -VAL[p[1]])
        size, step = 24, 22
        if pieces:
            step = min(step, max(14, avail // len(pieces)))
            size = min(size, step + 2)
        for p in pieces:
            small = pygame.transform.smoothscale(self.piece_surface(p), (size, size))
            s.blit(small, (px, y + 2))
            px += step

        diff = self._material_diff()
        if (side == "w" and diff > 0) or (side == "b" and diff < 0):
            text_blit(s, f"+{abs(diff)}", self.f_bodyb, C.GOOD,
                      (self.cap_rect.right, y + 12), "topright")

    def _material_diff(self):
        w = sum(VAL[p[1]] for p in self.captured["w"])
        b = sum(VAL[p[1]] for p in self.captured["b"])
        return (w - b) // 100

    # --- loop ---------------------------------------------------------------
    def run(self):
        running = True
        while running:
            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    running = False
                elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                    self.on_click(e.pos)
                elif e.type == pygame.KEYDOWN:
                    if e.key == pygame.K_ESCAPE:
                        running = False
                    elif e.key == pygame.K_n:
                        self.new_game()
                    elif e.key == pygame.K_u:
                        self.undo()
                    elif e.key == pygame.K_1:
                        self.level = "easy"
                    elif e.key == pygame.K_2:
                        self.level = "medium"
                    elif e.key == pygame.K_3:
                        self.level = "hard"

            self._pump_ai()
            self._update_anim()
            self.draw()
            pygame.display.flip()
            self.clock.tick(FPS)

        pygame.quit()
        sys.exit()


if __name__ == "__main__":
    sys.setrecursionlimit(10000)
    App().run()
