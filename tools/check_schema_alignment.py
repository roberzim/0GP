
#!/usr/bin/env python3
from __future__ import annotations
import sqlite3, sys, json
from typing import Dict, List, Tuple
import os

MAIN_TABLES = [
    'pratiche', 'pratica_avvocati', 'scadenze', 'attivita',
    'documenti', 'pratica_tariffe', 'history'
]

def open_conn(path: str) -> sqlite3.Connection:
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    return con

def table_cols(con: sqlite3.Connection, table: str) -> List[str]:
    cur = con.execute(f"PRAGMA table_info({table})")
    return [r[1] for r in cur.fetchall()]

def list_user_tables(con: sqlite3.Connection) -> List[str]:
    cur = con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY 1")
    return [r[0] for r in cur.fetchall()]

def analyze(path: str) -> Dict[str, object]:
    con = open_conn(path)
    all_tables = list_user_tables(con)
    report = {
        'db_path': os.path.abspath(path),
        'tables': all_tables,
        'main_tables_missing': [],
        'uses_pratica_id_only': [],
        'ok_id_pratica': [],
        'no_pratica_col': [],
    }
    for t in all_tables:
        cols = set(table_cols(con, t))
        if 'id_pratica' in cols:
            report['ok_id_pratica'].append(t)
        elif 'pratica_id' in cols:
            report['uses_pratica_id_only'].append(t)
        else:
            report['no_pratica_col'].append(t)
    for t in MAIN_TABLES:
        if t in all_tables:
            if 'id_pratica' not in set(table_cols(con, t)):
                report['main_tables_missing'].append(t)
        else:
            # non esiste: non segnaliamo ma può essere creato in installazioni minime
            pass
    con.close()
    return report

def main(argv: List[str]) -> int:
    if len(argv) != 2:
        print("Uso: check_schema_alignment.py <path_db.sqlite>")
        return 2
    path = argv[1]
    rep = analyze(path)
    print(json.dumps(rep, indent=2, ensure_ascii=False))
    # Exit code 0 sempre: è solo report
    return 0

if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
