#!/usr/bin/env python3
from __future__ import annotations
import os, sqlite3
from contextlib import contextmanager
from typing import Optional

PRAGMAS = [
    ("foreign_keys", "ON"),
    ("journal_mode", "WAL"),
    ("synchronous", "NORMAL"),
    ("temp_store", "MEMORY"),
]

@contextmanager
def get_connection(db_path: str):
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    con = sqlite3.connect(db_path, isolation_level=None)  # autocommit mode; we'll handle BEGIN manually
    try:
        for k, v in PRAGMAS:
            try:
                con.execute(f"PRAGMA {k}={v};")
            except Exception:
                pass
        yield con
    finally:
        con.close()

@contextmanager
def atomic_tx(con: sqlite3.Connection):
    try:
        con.execute("BEGIN")
        yield con
        con.execute("COMMIT")
    except Exception:
        try:
            con.execute("ROLLBACK")
        except Exception:
            pass
        raise

def initialize_schema(db_path: str, schema_path: Optional[str] = None, schema_sql: Optional[str] = None):
    if not schema_sql:
        if not schema_path:
            schema_path = "db_schema.sql"
        with open(schema_path, "r", encoding="utf-8") as f:
            schema_sql = f.read()
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    with get_connection(db_path) as con:
        con.executescript(schema_sql)
