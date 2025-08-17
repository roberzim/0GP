
from __future__ import annotations
import sqlite3
from typing import Optional, Any

def pragma_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    cur = conn.execute(f"PRAGMA table_info({table})")
    return [row[1] for row in cur.fetchall()]

def list_user_tables(conn: sqlite3.Connection) -> list[str]:
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY 1")
    return [r[0] for r in cur.fetchall()]

def find_pratica_column(conn: sqlite3.Connection, table: str) -> Optional[str]:
    cols = set(pragma_columns(conn, table))
    if 'id_pratica' in cols:
        return 'id_pratica'
    if 'pratica_id' in cols:
        return 'pratica_id'
    return None

def resolve_id_pratica(row: Any) -> Optional[str]:
    """Ritorna l'id pratica da una riga, indipendentemente che il campo si chiami id_pratica o pratica_id.
    Supporta sqlite3.Row, dict e oggetti generici.
    Priorità: id_pratica > pratica_id.
    """
    try:
        # sqlite3.Row o mappabili
        if hasattr(row, 'keys'):
            keys = set(k for k in row.keys())
            if 'id_pratica' in keys:
                return row['id_pratica']
            if 'pratica_id' in keys:
                return row['pratica_id']
    except Exception:
        pass
    # dict
    if isinstance(row, dict):
        return row.get('id_pratica') or row.get('pratica_id')
    # oggetto generico
    try:
        if hasattr(row, 'id_pratica'):
            return getattr(row, 'id_pratica')
        if hasattr(row, 'pratica_id'):
            return getattr(row, 'pratica_id')
    except Exception:
        pass
    return None

def quote_sql(v: Any) -> str:
    if v is None:
        return 'NULL'
    if isinstance(v, (int, float)):
        return str(v)
    s = str(v).replace("'", "''")
    return f"'{s}'"
