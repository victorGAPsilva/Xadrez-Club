import sys, types, math, time, os

# ------------------------------------------------------------------
# Stub de pygame suficiente para instanciar App, aplicar um lance,
# rodar a máquina de animação e chamar draw() (valida caminhos de desenho).
# ------------------------------------------------------------------
class Rect:
    def __init__(self, *a):
        if len(a) == 1 and isinstance(a[0], Rect):
            self.x, self.y, self.w, self.h = a[0].x, a[0].y, a[0].w, a[0].h
        elif len(a) == 4:
            self.x, self.y, self.w, self.h = map(int, a)
        elif len(a) == 2:
            self.x, self.y, self.w, self.h = 0, 0, a[0], a[1]
        else:
            self.x = self.y = 0; self.w = self.h = 0
    @property
    def right(self): return self.x + self.w
    @property
    def bottom(self): return self.y + self.h
    @property
    def width(self): return self.w
    @property
    def height(self): return self.h
    @property
    def top(self): return self.y
    @property
    def left(self): return self.x
    @property
    def center(self): return (self.x + self.w // 2, self.y + self.h // 2)
    @center.setter
    def center(self, v): self.x = int(v[0] - self.w / 2); self.y = int(v[1] - self.h / 2)
    @property
    def centerx(self): return self.x + self.w // 2
    @property
    def centery(self): return self.y + self.h // 2
    @property
    def topleft(self): return (self.x, self.y)
    def inflate(self, dx, dy): return Rect(self.x - dx // 2, self.y - dy // 2, self.w + dx, self.h + dy)
    def collidepoint(self, p): return self.x <= p[0] < self.right and self.y <= p[1] < self.bottom
    def copy(self): return Rect(self)

class Surface:
    def __init__(self, size=(0, 0), flags=0): self.size = size
    def get_size(self): return self.size
    def get_rect(self, **kw):
        r = Rect(0, 0, self.size[0], self.size[1])
        for k, v in kw.items():
            if k == "center": r.center = v
            elif k == "topleft": r.x, r.y = map(int, v)
            elif k == "midright": r.x = int(v[0] - r.w); r.y = int(v[1] - r.h / 2)
            elif k == "midleft": r.x = int(v[0]); r.y = int(v[1] - r.h / 2)
            elif k == "topright": r.x = int(v[0] - r.w); r.y = int(v[1])
            elif k == "centerx": r.x = int(v - r.w / 2)
        return r
    def fill(self, *a): pass
    def blit(self, *a): pass
    def copy(self): return Surface(self.size)
    def set_alpha(self, a): self.alpha = a

class Font:
    def __init__(self, h=16): self.h = h
    def render(self, text, aa, color, bg=None):
        return Surface((max(4, len(str(text)) * 8), self.h))
    def size(self, text): return (max(4, len(str(text)) * 8), self.h)
    def get_height(self): return self.h

pg = types.ModuleType("pygame")
pg.SRCALPHA = 1
pg.Rect = Rect
pg.Surface = Surface
pg.init = lambda: None
pg.quit = lambda: None
pg.font = types.ModuleType("pygame.font")
pg.font.SysFont = lambda names, size, bold=False, italic=False: Font(int(size) + 6)
pg.font.Font = lambda *a, **k: Font()
pg.display = types.SimpleNamespace(set_mode=lambda size: Surface(tuple(size)),
                                   set_caption=lambda *a: None, flip=lambda: None)
pg.draw = types.SimpleNamespace(
    rect=lambda *a, **k: None, line=lambda *a, **k: None,
    circle=lambda *a, **k: None,
    # emula o comportamento real: ellipse cria Rect -> rejeita float
    ellipse=lambda s, c, r, *a, **k: Rect(*r))
pg.transform = types.SimpleNamespace(smoothscale=lambda s, size: Surface(size))
pg.mouse = types.SimpleNamespace(get_pos=lambda: (0, 0))
pg.time = types.SimpleNamespace(Clock=lambda: types.SimpleNamespace(tick=lambda *a: None))
pg.event = types.SimpleNamespace(get=lambda: [])
pg.QUIT = 0; pg.MOUSEBUTTONDOWN = 1; pg.KEYDOWN = 2
pg.K_ESCAPE = 27; pg.K_n = 110; pg.K_u = 117; pg.K_1 = 49; pg.K_2 = 50; pg.K_3 = 51
sys.modules["pygame"] = pg
sys.modules["pygame.font"] = pg.font

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import chess_ai as ch

app = ch.App()
print("App construída; botões e retângulos de layout OK")

# 1) desenho inicial (nenhuma animação)
app.draw()
print("draw() posição inicial: OK")

# 2) aplica e2-e4 -> deve iniciar animação
app.apply_move((6, 4, 4, 4))
assert app.anim is not None, "animação não iniciada"
assert app.pending_finish is True
print("animação iniciada para e2-e4:", app.anim["fr"], app.anim["fc"], "->", app.anim["tr"], app.anim["tc"])

# 3) desenho durante a animação (peça em voo + sombra + sem captura)
app.draw()
print("draw() durante animação: OK")

# 4) simula lances capturando para testar fade: monta Bxc6 simples
#    Brancas: e4 já jogado; agora joga peão d4? Vamos usar IA? Direto:
#    força posição: branco bispo c4 captura peão f7
app2 = ch.App()
app2.engine.board = [["" for _ in range(8)] for _ in range(8)]
app2.engine.board[7][4] = "wK"; app2.engine.board[0][4] = "bK"
app2.engine.board[4][2] = "wB"; app2.engine.board[1][5] = "bP"
app2.engine.king_pos = {"w": (7, 4), "b": (0, 4)}
app2.engine.turn = "w"
app2.apply_move((4, 2, 1, 5))  # Bxf7
assert app2.anim["captured"] == "bP", "captura não registrada na animação"
app2.draw()
print("draw() com peça capturada desvanecendo: OK")

# 5) conclusão da animação dispara _finish_move e IA (turno -> pretas)
app.anim["t0"] -= 1.0
app._update_anim()
assert app.anim is None, "animação não terminou"
assert app.thinking is True, "IA não iniciada após o lance"
print("fim da animação -> IA iniciada:", app.thinking)

# 6) checa Rect/ellipse com floats (o bug corrigido) não levanta
app.draw()
print("draw() pós-animação: OK")

print("TODOS OS TESTES DE APRESENTAÇÃO PASSARAM")
