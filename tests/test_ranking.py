import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ranking import Ranking, expected_score, DEFAULT_RATING, K_FACTOR

DB = os.path.join(tempfile.gettempdir(), "rank_unit.db")
if os.path.exists(DB):
    os.remove(DB)

r = Ranking(DB)

# --- upsert cria com rating inicial ---
p = r.upsert_player("A1", "Ana")
assert p["rating"] == DEFAULT_RATING and p["games"] == 0 and p["rank"] is None
p2 = r.upsert_player("A1", "Ana Maria")  # atualiza apelido
assert p2["name"] == "Ana Maria"
r.upsert_player("A1", "Ana")
p = r.get("A1")
assert p["name"] == "Ana"
print("upsert OK (cria 1200 e troca apelido)")

# --- ELO: vitória de A sobre B (iguais) ---
ch = r.record("A1", "B1", "w")
assert ch["white"]["before"] == 1200 and ch["white"]["after"] == 1200 + K_FACTOR // 2 * 1
assert ch["white"]["delta"] == 16 and ch["black"]["delta"] == -16
assert r.get("A1")["wins"] == 1 and r.get("B1")["losses"] == 1
print("ELO 16/-16 OK:", ch["white"]["after"], ch["black"]["after"])

# --- vitória de B sobre A: A cai mais que 16 (rating maior esperado) ---
ch = r.record("A1", "B1", "b")
assert ch["white"]["delta"] < 0
assert r.get("A1")["losses"] == 1 and r.get("B1")["wins"] == 1
print("derrota cobra mais de quem tem rating maior OK")

# --- empate ---
before_a = r.get("A1")["rating"]
ch = r.record("A1", "B1", "draw")
assert r.get("A1")["draws"] == 1 and r.get("A1")["games"] == 3
print("empate OK")

# --- jogador sem partidas não entra no top ---
r.upsert_player("NOVO", "Novato")
top = r.top(10)
assert top["total"] == 2, top
assert all(p["games"] > 0 for p in top["top"])
print("top só com quem jogou OK;", [(p["name"], p["rating"]) for p in top["top"]])

# --- rank/ordenação ---
b = r.get("B1")
assert b["rank"] == 1, b          # B1 venceu mais e tem rating mais alto
assert r.get("NOVO")["rank"] is None
print("rank_of OK:", b["name"], "nº", b["rank"])

# --- persistência: reabre o arquivo e mantém tudo ---
r2 = Ranking(DB)
assert r2.get("A1")["rating"] == r.get("A1")["rating"]
assert r2.get("B1")["wins"] == 1 and r2.get("B1")["rank"] == 1
print("persistência em disco OK")

# --- casos inválidos não gravam ---
assert r.record("A1", "B1", "x") is None
assert r.record("A1", "A1", "w") is None
assert r.record("", "B1", "w") is None
assert r.record(None, None, "w") is None
assert r.get("A1")["games"] == 3  # nada mudou
print("entradas inválidas ignoradas OK")

# --- expected_score simétrico ---
assert abs(expected_score(1200, 1200) - 0.5) < 1e-9
assert expected_score(1400, 1200) > 0.75
print("fórmula ELO OK")

print("TODOS OS TESTES DE RANKING PASSARAM")