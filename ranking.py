# -*- coding: utf-8 -*-
"""
Rank mundial do Xadrez — Edição de Clube.

Placar global persistente em SQLite (biblioteca padrão, sem dependências),
com rating **ELO** (começa em 1200). Só contam partidas **online** entre humanos.

O banco fica, por padrão, em `~/.xadrez/ranking.db` — fora do OneDrive, que
atrapalha arquivos sincronizados. Para apontar para outro lugar (ex.: um disco
no Render), defina a variável de ambiente `XADREZ_DB`.
"""

import os
import sqlite3
import threading
from datetime import datetime, timezone

DEFAULT_RATING = 1200
K_FACTOR = 32  # o quanto cada partida mexe no rating

SCHEMA = """
CREATE TABLE IF NOT EXISTS players (
    id         TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    rating     INTEGER NOT NULL DEFAULT 1200,
    games      INTEGER NOT NULL DEFAULT 0,
    wins       INTEGER NOT NULL DEFAULT 0,
    losses     INTEGER NOT NULL DEFAULT 0,
    draws      INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_players_rating ON players(rating DESC);
"""


def default_path():
    env = os.environ.get("XADREZ_DB")
    if env:
        return env
    return os.path.join(os.path.expanduser("~"), ".xadrez", "ranking.db")


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def expected_score(rating_a, rating_b):
    """Probabilidade esperada de A vencer B (fórmula ELO)."""
    return 1.0 / (1.0 + 10 ** ((rating_b - rating_a) / 400.0))


class Ranking:
    def __init__(self, path=None):
        self.path = path or default_path()
        if self.path != ":memory:":
            os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._conn.commit()

    # ------------------------------- leitura -------------------------------
    def _row(self, pid):
        cur = self._conn.execute("SELECT * FROM players WHERE id = ?", (pid,))
        row = cur.fetchone()
        return dict(row) if row else None

    def get(self, pid):
        with self._lock:
            row = self._row(pid)
        if not row:
            return None
        return self._profile(row)

    def _profile(self, row):
        prof = {
            "id": row["id"],
            "name": row["name"],
            "rating": row["rating"],
            "games": row["games"],
            "wins": row["wins"],
            "losses": row["losses"],
            "draws": row["draws"],
            "rank": None,
        }
        if row["games"] > 0:
            prof["rank"] = self.rank_of(row["id"])
        return prof

    def _ranked_ids(self):
        cur = self._conn.execute(
            "SELECT id FROM players WHERE games > 0 "
            "ORDER BY rating DESC, wins DESC, games ASC, name ASC")
        return [r["id"] for r in cur.fetchall()]

    def rank_of(self, pid):
        ids = self._ranked_ids()
        try:
            return ids.index(pid) + 1
        except ValueError:
            return None

    def top(self, limit=50, offset=0):
        limit = max(1, min(int(limit), 200))
        offset = max(0, int(offset))
        with self._lock:
            total = self._conn.execute(
                "SELECT COUNT(*) AS n FROM players WHERE games > 0").fetchone()["n"]
            rows = self._conn.execute(
                "SELECT * FROM players WHERE games > 0 "
                "ORDER BY rating DESC, wins DESC, games ASC, name ASC "
                "LIMIT ? OFFSET ?", (limit, offset)).fetchall()
            out = []
            for i, row in enumerate(rows):
                prof = self._profile(dict(row))
                prof["rank"] = offset + i + 1
                out.append(prof)
            return {"top": out, "total": total}

    # ------------------------------- escrita -------------------------------
    def upsert_player(self, pid, name=None):
        """Cria o jogador (rating inicial) ou atualiza o apelido. Devolve o perfil."""
        if not pid:
            return None
        name = (name or "").strip()[:20]
        with self._lock:
            row = self._row(pid)
            if row is None:
                self._conn.execute(
                    "INSERT INTO players(id, name, rating, games, wins, losses, draws, updated_at) "
                    "VALUES(?,?,?,0,0,0,0,?)",
                    (pid, name or "Anônimo", DEFAULT_RATING, _now()))
                self._conn.commit()
            elif name and name != row["name"]:
                self._conn.execute(
                    "UPDATE players SET name = ?, updated_at = ? WHERE id = ?",
                    (name, _now(), pid))
                self._conn.commit()
            return self._profile(self._row(pid))

    def _bump(self, pid, new_rating, outcome):
        col = {"w": "wins", "l": "losses", "d": "draws"}[outcome]
        self._conn.execute(
            "UPDATE players SET rating = ?, games = games + 1, %s = %s + 1, updated_at = ? "
            "WHERE id = ?" % (col, col),
            (new_rating, _now(), pid))

    def record(self, white_pid, black_pid, result):
        """Registra o resultado de uma partida.

        result: "w" (brancas vencem), "b" (pretas vencem) ou "draw".
        Devolve os dois perfis com antes/depois, ou None se não for válido.
        """
        if not white_pid or not black_pid or white_pid == black_pid:
            return None
        if result not in ("w", "b", "draw"):
            return None

        with self._lock:
            w = self._row(white_pid) or self._create_locked(white_pid)
            b = self._row(black_pid) or self._create_locked(black_pid)
            wr, br = w["rating"], b["rating"]

            ew = expected_score(wr, br)
            eb = 1.0 - ew
            if result == "w":
                sw, sb = 1.0, 0.0
            elif result == "b":
                sw, sb = 0.0, 1.0
            else:
                sw = sb = 0.5

            nw = int(round(wr + K_FACTOR * (sw - ew)))
            nb = int(round(br + K_FACTOR * (sb - eb)))

            self._bump(white_pid, nw, "w" if result == "w" else "l" if result == "b" else "d")
            self._bump(black_pid, nb, "w" if result == "b" else "l" if result == "w" else "d")
            self._conn.commit()

            return {
                "result": result,
                "white": {"id": white_pid, "name": w["name"], "before": wr, "after": nw,
                          "delta": nw - wr},
                "black": {"id": black_pid, "name": b["name"], "before": br, "after": nb,
                          "delta": nb - br},
            }

    def _create_locked(self, pid):
        self._conn.execute(
            "INSERT INTO players(id, name, rating, games, wins, losses, draws, updated_at) "
            "VALUES(?,?,?,0,0,0,0,?)",
            (pid, "Anônimo", DEFAULT_RATING, _now()))
        self._conn.commit()
        return self._row(pid)


# Instância única. Se o disco falhar, cai para memória (não derruba o servidor).
try:
    RANKING = Ranking()
except Exception as exc:  # noqa: BLE001
    print("[ranking] aviso: não deu para abrir o banco (%s); usando memória." % exc)
    RANKING = Ranking(":memory:")
