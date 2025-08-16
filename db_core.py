# db_core.py
from __future__ import annotations
import sqlite3
from contextlib import contextmanager
from pathlib import Path

_PRAGMAS = (
    "PRAGMA journal_mode=WAL;",
    "PRAGMA synchronous=NORMAL;",
    "PRAGMA foreign_keys=ON;",
    "PRAGMA temp_store=MEMORY;",
)

def _apply_pragmas(con: sqlite3.Connection) -> None:
    cur = con.cursor()
    for p in _PRAGMAS:
        cur.execute(p)
    cur.close()

@contextmanager
def get_connection(db_path: str):
    """Apre una connessione SQLite con PRAGMA applicati."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    _apply_pragmas(con)
    try:
        yield con
    finally:
        con.close()

@contextmanager
def atomic_tx(con: sqlite3.Connection):
    """Transazione atomica (BEGIN/COMMIT/ROLLBACK)."""
    try:
        con.execute("BEGIN")
        yield con
    except Exception:
        con.execute("ROLLBACK")
        raise
    else:
        con.execute("COMMIT")

def initialize_schema(db_path: str, schema_path: str = "db_schema.sql") -> None:
    """
    Crea/aggiorna lo schema del DB leggendo da db_schema.sql.
    Se il file non esiste, usa uno schema minimo di fallback.
    """
    schema_file = Path(schema_path)
    if schema_file.exists():
        sql = schema_file.read_text(encoding="utf-8")
    else:
        # Fallback minimale: solo tabella pratiche
        sql = """
        CREATE TABLE IF NOT EXISTS pratiche (
            id_pratica TEXT PRIMARY KEY,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT
        );
        """
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as con:
        _apply_pragmas(con)
        con.executescript(sql)

__all__ = [
    "get_connection",
    "atomic_tx",
    "initialize_schema",
]

