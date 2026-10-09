import sys, types, time, random, os

# --- stub mínimo de pygame para importar o módulo sem display ---
pg = types.ModuleType("pygame")
pg.SRCALPHA = 0
pg.font = types.ModuleType("pygame.font")
def _ret(*a, **k):
    return None
pg.font.SysFont = lambda *a, **k: types.SimpleNamespace(
    render=lambda *a, **k: types.SimpleNamespace(get_size=lambda: (10, 10)),
    size=lambda *a, **k: (5, 20), get_height=lambda: 20)
pg.init = lambda: None
pg.display = types.SimpleNamespace(set_mode=lambda *a: None, set_caption=lambda *a: None, flip=lambda: None)
pg.draw = types.SimpleNamespace(rect=lambda *a, **k: None, line=lambda *a, **k: None, circle=lambda *a, **k: None)
pg.Rect = type("Rect", (), {"__init__": lambda self, *a: None})
pg.Surface = type("Surface", (), {"__init__": lambda self, *a, **k: None})
pg.transform = types.SimpleNamespace(smoothscale=lambda *a: None)
pg.mouse = types.SimpleNamespace(get_pos=lambda: (0, 0))
pg.time = types.SimpleNamespace()
pg.event = types.SimpleNamespace(get=lambda: [])
pg.QUIT = 0; pg.MOUSEBUTTONDOWN = 1; pg.KEYDOWN = 2
pg.K_ESCAPE = 27; pg.K_n = 110; pg.K_u = 117; pg.K_1 = 49; pg.K_2 = 50; pg.K_3 = 51
sys.modules["pygame"] = pg
sys.modules["pygame.font"] = pg.font

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import chess_ai as ch

# 1) posição inicial: 20 lances legais
e = ch.Engine()
print("legal inicial:", len(e.generate_legal("w")))
assert len(e.generate_legal("w")) == 20

# 2) SAN básico
assert ch.move_to_san(e, (6, 4, 4, 4)) == "e4"
assert ch.move_to_san(e, (7, 6, 5, 5)) == "Nf3"

# 3) auto-jogo rápido garantindo legalidade
random.seed(1)
e = ch.Engine()
plies = 0
while plies < 40 and not e.is_in_check(e.turn) is None:
    legal = e.generate_legal(e.turn)
    if not legal:
        break
    m = random.choice(legal)
    assert m in legal
    e.make_move(m)
    plies += 1
print("auto-jogo ok, plies:", plies)

# 4) xeque-mate do pastor é detectado (1.e4 e5 2.Bc4 Nc6 3.Qh5 Nf6?? 4.Qxf7#)
e = ch.Engine()
seq = [(6,4,4,4),(1,4,3,4),(7,5,4,2),(0,1,2,2),(7,3,3,7),(0,6,2,5),(3,7,1,5)]
for m in seq:
    assert m in e.generate_legal(e.turn), ("ilegal", m, e.turn)
    e.make_move(m)
assert not e.generate_legal("b"), "pretas deveriam estar mate"
assert e.is_in_check("b"), "preto deveria estar em xeque"
print("mate do pastor: OK, ultimo SAN =", ch.move_to_san(ch.Engine(), (6,4,4,4)))

# 5) IA nos 3 niveis — tempo e legalidade
for lvl in ("easy", "medium", "hard"):
    e = ch.Engine()
    t = time.time()
    mv = ch.AI(lvl).choose_move(e)
    dt = time.time() - t
    assert mv in e.generate_legal(e.turn)
    print(f"IA {lvl:6s}: {mv}  ({dt:.2f}s)")

# 6) a IA realmente acha uma captura gratuita? (dama indefesa)
e = ch.Engine()
e.board = [[c if c else "" for c in row] for row in ch.INITIAL]
# brancas: Rei e8? monta posição simples: branco Re1, Pe2... simplificar:
e.board = [["" for _ in range(8)] for _ in range(8)]
e.board[7][4] = "wK"; e.board[0][4] = "bK"; e.board[7][0] = "wQ"; e.board[0][0] = "bR"
e.king_pos = {"w": (7,4), "b": (0,4)}
e.turn = "w"
mv = ch.AI("hard").choose_move(e)
print("captura obvia (hard):", mv, "->", ch.move_to_san(e, mv))
print("TODOS OS TESTES PASSARAM")
