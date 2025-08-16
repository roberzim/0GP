# db_migrations.py
from __future__ import annotations
import sqlite3

CHILD_TABLES = {
    "attivita":         ["id_pratica","uid","pos","inizio","fine","descrizione","durata_min","tariffa_eur","tipo","note"],
    "scadenze":         ["id_pratica","uid","pos","data_scadenza","descrizione","note","completata"],
    "documenti":        ["id_pratica","uid","pos","path","categoria","note","hash"],
    "pratica_tariffe":  ["id_pratica","uid","pos","tipo_tariffa","valore","note"],
    "pratica_avvocati": ["id_pratica","uid","pos","email","nome","ruolo"],
}

def column_exists(con: sqlite3.Connection, table: str, col: str) -> bool:
    return any(r[1] == col for r in con.execute(f"PRAGMA table_info({table})"))

def ensure_columns(con: sqlite3.Connection) -> None:
    for t in CHILD_TABLES.keys():
        if not column_exists(con, t, "uid"):
            con.execute(f"ALTER TABLE {t} ADD COLUMN uid TEXT")
        if not column_exists(con, t, "pos"):
            con.execute(f"ALTER TABLE {t} ADD COLUMN pos INTEGER")
        # indice (univoco su uid per tabella)
        con.execute(f"CREATE UNIQUE INDEX IF NOT EXISTS uq_{t}_uid ON {t}(uid)")
        # ordina e ricerche veloci
        con.execute(f"CREATE INDEX IF NOT EXISTS idx_{t}_pos ON {t}(id_pratica, pos)")
    con.commit()

def backfill_uids(con: sqlite3.Connection) -> None:
    # genera uid su righe storiche senza uid
    for t in CHILD_TABLES.keys():
        con.execute(f"UPDATE {t} SET uid = lower(hex(randomblob(16))) WHERE uid IS NULL OR uid = ''")
        # pos di default = rowid se non presente
        con.execute(f"UPDATE {t} SET pos = COALESCE(pos, rowid)")
    con.commit()

def run_migrations(db_path: str) -> None:
    with sqlite3.connect(db_path) as con:
        con.execute("PRAGMA foreign_keys=ON;")
        ensure_columns(con)
        backfill_uids(con)

