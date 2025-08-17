#!/usr/bin/env python3
from __future__ import annotations
import sqlite3, re

def import_pratica_sql(db_path: str, sql_text: str) -> tuple[bool, str|None]:
    con = sqlite3.connect(db_path)
    con.execute('PRAGMA foreign_keys = ON;')
    try:
        with con:
            before = con.total_changes
            con.executescript(sql_text)
            after = con.total_changes
            changed = (after - before) > 0
    finally:
        con.close()
    m = re.search(r"Export pratica\s+([^\s]+)", sql_text)
    return changed, (m.group(1) if m else None)
