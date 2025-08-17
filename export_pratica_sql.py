
#!/usr/bin/env python3
"""
Export SQL per una singola pratica (idempotente e completo).
Requisiti rispettati:
- Include tutte le colonne per ogni tabella che contiene 'id_pratica' o 'pratica_id' (ordine da PRAGMA).
- Per ogni tabella genera "DELETE WHERE <col>=<id>" seguito da "INSERT INTO (...) VALUES (...);" per ogni riga.
- Aggiunge sempre commenti di header e, se non esporta alcuna riga, un commento finale per evitare file vuoto.
- Filtra usando l'id "raw" passato dall'utente (nessuna normalizzazione).
- Non modifica lo schema del DB.
"""
from __future__ import annotations
import sqlite3, datetime, os
from typing import List, Tuple
from sql_utils import find_pratica_column, pragma_columns, quote_sql, list_user_tables

def _connect(db_path: str) -> sqlite3.Connection:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    return con

def _tables_with_pratica_key(con: sqlite3.Connection) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for t in list_user_tables(con):
        col = find_pratica_column(con, t)
        if col:
            pairs.append((t, col))
    return pairs

def export_pratica_sql(db_path: str, idp: str) -> str:
    try:
        con = _connect(db_path)
    except Exception as e:
        return f"-- Errore apertura DB {db_path!r}: {e}\n"
    try:
        pairs = _tables_with_pratica_key(con)
        header = [
            f"-- Export pratica {idp}",
            f"-- Database: {os.path.abspath(db_path)}",
            f"-- Generato: {datetime.datetime.now().isoformat(timespec='seconds')}",
            f"-- Tabelle coinvolte: {', '.join(t for t,_ in pairs) if pairs else '(nessuna)'}",
            "BEGIN;"
        ]
        out: List[str] = header
        total = 0
        for t, pratica_col in pairs:
            rows = con.execute(f"SELECT * FROM {t} WHERE {pratica_col}=?", (idp,)).fetchall()
            cols = pragma_columns(con, t)
            out.append(f"-- {t}")
            out.append(f"DELETE FROM {t} WHERE {pratica_col}={quote_sql(idp)};")
            for r in rows:
                vals = [r[c] if (hasattr(r, 'keys') and c in r.keys()) else None for c in cols]
                out.append(f"INSERT INTO {t} ({', '.join(cols)}) VALUES ({', '.join(quote_sql(v) for v in vals)});")
            total += len(rows)
        out.append("COMMIT;")
        if total == 0:
            out.append(f"-- Nessuna riga esportata per pratica {idp}")
        out.append("")
        return "\n".join(out)
    finally:
        try:
            con.close()
        except Exception:
            pass

if __name__ == '__main__':
    import sys
    if len(sys.argv) != 3:
        sys.stderr.write('Uso: export_pratica_sql.py <path_db.sqlite> <id_pratica>\n')
        sys.exit(2)
    print(export_pratica_sql(sys.argv[1], sys.argv[2]), end='')
