from __future__ import annotations
import sqlite3
from typing import Any, Iterable

def _q(v: Any) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, (int, float)):
        return str(v)
    s = str(v)
    return "'" + s.replace("'", "''") + "'"

def _colnames(conn: sqlite3.Connection, table: str) -> list[str]:
    """
    Ritorna i nomi delle colonne della tabella nell'ordine definito,
    usando PRAGMA table_info(<table>). L'indice 1 è il nome (stringa).
    """
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    names: list[str] = []
    for r in rows:
        # r è tipicamente una tupla: (cid:int, name:str, type:str, ...)
        try:
            names.append(r[1])
        except Exception:
            # fallback prudente
            n = r["name"] if hasattr(r, "keys") and "name" in r.keys() else str(r[1])
            names.append(n)
    return names

def render_pratica_sql(conn: sqlite3.Connection, id_pratica: str) -> str:
    # Assicura Row factory per accesso per nome
    try:
        conn.row_factory = sqlite3.Row
    except Exception:
        pass

    # Pratica
    pr = conn.execute("SELECT * FROM pratiche WHERE id_pratica=?", (id_pratica,)).fetchone()
    if not pr:
        return "BEGIN;\n-- Nessuna pratica trovata\nCOMMIT;\n"

    cols_p = _colnames(conn, "pratiche")
    vals_p = [pr[c] if (hasattr(pr, "keys") and c in pr.keys()) else None for c in cols_p]
    ins_p  = f"INSERT INTO pratiche ({', '.join(cols_p)}) VALUES ({', '.join(_q(v) for v in vals_p)});"

    # Scadenze
    sc_rows = conn.execute(
        "SELECT * FROM scadenze WHERE id_pratica=? ORDER BY pos, id",
        (id_pratica,)
    ).fetchall()
    sc_sql: list[str] = []
    if sc_rows:
        cols_s = _colnames(conn, "scadenze")
        for r in sc_rows:
            vals = [r[c] if (hasattr(r, "keys") and c in r.keys()) else None for c in cols_s]
            sc_sql.append(
                f"INSERT INTO scadenze ({', '.join(cols_s)}) VALUES ({', '.join(_q(v) for v in vals)});"
            )

    # Documenti
    dc_rows = conn.execute(
        "SELECT * FROM documenti WHERE id_pratica=? ORDER BY pos, id",
        (id_pratica,)
    ).fetchall()
    dc_sql: list[str] = []
    if dc_rows:
        cols_d = _colnames(conn, "documenti")
        for r in dc_rows:
            vals = [r[c] if (hasattr(r, "keys") and c in r.keys()) else None for c in cols_d]
            dc_sql.append(
                f"INSERT INTO documenti ({', '.join(cols_d)}) VALUES ({', '.join(_q(v) for v in vals)});"
            )

    parts = [
        "BEGIN;",
        "-- pratica",
        ins_p,
        "-- scadenze",
        *sc_sql,
        "-- documenti",
        *dc_sql,
        "COMMIT;",
        "",
    ]
    return "\n".join(parts)
