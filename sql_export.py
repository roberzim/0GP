
from __future__ import annotations
import sqlite3, datetime
from typing import List
from sql_utils import pragma_columns, quote_sql, find_pratica_column

def render_pratica_sql(conn: sqlite3.Connection, id_pratica: str) -> str:
    try:
        conn.row_factory = sqlite3.Row
    except Exception:
        pass

    parts: List[str] = [
        f"-- Export pratica {id_pratica}",
        f"-- Generato: {datetime.datetime.now().isoformat(timespec='seconds')}" ,
        "BEGIN;",
    ]

    # Pratiche (se esiste)
    try:
        cols_p = pragma_columns(conn, 'pratiche')
        if cols_p:
            pr = conn.execute("SELECT * FROM pratiche WHERE id_pratica=?", (id_pratica,)).fetchone()
            parts.append("-- pratiche")
            parts.append(f"DELETE FROM pratiche WHERE id_pratica={quote_sql(id_pratica)};")
            if pr:
                vals_p = [pr[c] if (hasattr(pr, 'keys') and c in pr.keys()) else None for c in cols_p]
                parts.append(f"INSERT INTO pratiche ({', '.join(cols_p)}) VALUES ({', '.join(quote_sql(v) for v in vals_p)});")
    except Exception:
        pass

    # Altre tabelle correlate
    table_rows = 0
    for (t,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name != 'pratiche' ORDER BY 1"):
        pratica_col = find_pratica_column(conn, t)
        if not pratica_col:
            continue
        rows = conn.execute(f"SELECT * FROM {t} WHERE {pratica_col}=? ORDER BY 1", (id_pratica,)).fetchall()
        cols = pragma_columns(conn, t)
        parts.append(f"-- {t}")
        parts.append(f"DELETE FROM {t} WHERE {pratica_col}={quote_sql(id_pratica)};")
        for r in rows:
            vals = [r[c] if (hasattr(r, 'keys') and c in r.keys()) else None for c in cols]
            parts.append(f"INSERT INTO {t} ({', '.join(cols)}) VALUES ({', '.join(quote_sql(v) for v in vals)});")
        table_rows += len(rows)

    parts.append("COMMIT;")
    if table_rows == 0:
        parts.append(f"-- Nessuna riga figlia trovata per pratica {id_pratica}")
    parts.append("")
    return "\n".join(parts)
