#!/usr/bin/env python3
from __future__ import annotations

# Rende importabile db_core dalla cartella padre
import os, sys, sqlite3
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db_core import get_db_path, connect

def _cols(con: sqlite3.Connection, table: str) -> set[str]:
    cur = con.execute(f"PRAGMA table_info({table})")
    return {r[1] for r in cur.fetchall()}

def _add_col(con: sqlite3.Connection, table: str, name: str, decl: str) -> bool:
    if name in _cols(con, table):
        return False
    con.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")
    return True

def _ensure_table(con: sqlite3.Connection, create_sql: str):
    con.executescript(create_sql)

def ensure_min_schema(con: sqlite3.Connection) -> list[str]:
    changes: list[str] = []

    # --- pratiche ---
    _ensure_table(con, "CREATE TABLE IF NOT EXISTS pratiche(id_pratica TEXT PRIMARY KEY);")
    for name, decl in [
        ("anno","INTEGER"),
        ("numero","INTEGER"),
        ("titolo","TEXT"),          # <— aggiunto ora
        ("stato","TEXT"),           # <— aggiunto ora
        ("tipo_pratica","TEXT"),
        ("settore","TEXT"),
        ("materia","TEXT"),
        ("referente_email","TEXT"),
        ("referente_nome","TEXT"),
        ("preventivo","INTEGER DEFAULT 0"),
        ("note","TEXT"),
        ("created_at","TEXT DEFAULT (datetime('now'))"),
        ("updated_at","TEXT"),
        ("raw_json","TEXT"),
    ]:
        if _add_col(con, "pratiche", name, decl):
            changes.append(f"pratiche + {name}")

    # --- pratica_avvocati ---
    _ensure_table(con, "CREATE TABLE IF NOT EXISTS pratica_avvocati(id_pratica TEXT NOT NULL);")
    for name, decl in [("uid","TEXT"), ("pos","INTEGER DEFAULT 0"), ("email","TEXT"), ("nome","TEXT"), ("ruolo","TEXT")]:
        if _add_col(con, "pratica_avvocati", name, decl):
            changes.append(f"pratica_avvocati + {name}")
    con.execute("CREATE INDEX IF NOT EXISTS idx_pravv_pratica ON pratica_avvocati(id_pratica)")

    # --- pratica_tariffe ---
    _ensure_table(con, "CREATE TABLE IF NOT EXISTS pratica_tariffe(id_pratica TEXT NOT NULL);")
    for name, decl in [("uid","TEXT"), ("pos","INTEGER DEFAULT 0"), ("tipo_tariffa","TEXT"), ("valore","REAL"), ("note","TEXT")]:
        if _add_col(con, "pratica_tariffe", name, decl):
            changes.append(f"pratica_tariffe + {name}")
    con.execute("CREATE INDEX IF NOT EXISTS idx_ptar_pratica ON pratica_tariffe(id_pratica)")

    # --- attivita ---
    _ensure_table(con, "CREATE TABLE IF NOT EXISTS attivita(id INTEGER PRIMARY KEY AUTOINCREMENT, id_pratica TEXT NOT NULL);")
    for name, decl in [("uid","TEXT"), ("pos","INTEGER DEFAULT 0"), ("inizio","TEXT"), ("fine","TEXT"), ("descrizione","TEXT"),
                       ("durata_min","INTEGER"), ("tariffa_eur","REAL"), ("tipo","TEXT"), ("note","TEXT")]:
        if _add_col(con, "attivita", name, decl):
            changes.append(f"attivita + {name}")
    con.execute("CREATE INDEX IF NOT EXISTS idx_attivita_pratica ON attivita(id_pratica)")

    # --- scadenze ---
    _ensure_table(con, "CREATE TABLE IF NOT EXISTS scadenze(id INTEGER PRIMARY KEY AUTOINCREMENT, id_pratica TEXT NOT NULL);")
    for name, decl in [("uid","TEXT"), ("pos","INTEGER DEFAULT 0"), ("data_scadenza","TEXT"), ("descrizione","TEXT"),
                       ("note","TEXT"), ("completata","INTEGER DEFAULT 0")]:
        if _add_col(con, "scadenze", name, decl):
            changes.append(f"scadenze + {name}")
    con.execute("CREATE INDEX IF NOT EXISTS idx_scadenze_pratica ON scadenze(id_pratica)")

    # --- documenti ---
    _ensure_table(con, "CREATE TABLE IF NOT EXISTS documenti(id INTEGER PRIMARY KEY AUTOINCREMENT, id_pratica TEXT NOT NULL);")
    for name, decl in [("uid","TEXT"), ("pos","INTEGER DEFAULT 0"), ("path","TEXT"), ("categoria","TEXT"),
                       ("note","TEXT"), ("hash","TEXT")]:
        if _add_col(con, "documenti", name, decl):
            changes.append(f"documenti + {name}")
    con.execute("CREATE INDEX IF NOT EXISTS idx_documenti_pratica ON documenti(id_pratica)")

    return changes

def main() -> int:
    db_path = get_db_path()
    print("DB:", db_path)
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    with connect(db_path) as con:
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        ch = ensure_min_schema(con)
        if ch:
            print("Aggiornamenti applicati:"); [print(" -", c) for c in ch]
        else:
            print("Schema già allineato.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
