#!/usr/bin/env python3
from __future__ import annotations
import os, sqlite3, json
from typing import Optional, Dict, Any, List
from db_core import get_connection, initialize_schema, atomic_tx
import repo_sqlite

def _fetch_pratica_as_dict(con: sqlite3.Connection, id_pratica: str) -> Optional[Dict[str, Any]]:
    con.row_factory = sqlite3.Row
    row = con.execute("SELECT * FROM pratiche WHERE id_pratica=?", (id_pratica,)).fetchone()
    if not row:
        return None
    out: Dict[str, Any] = dict(row)
    out["avvocati"] = [dict(r) for r in con.execute(
        "SELECT uid,pos,ruolo,email,nome FROM pratica_avvocati WHERE id_pratica=? ORDER BY pos, uid", (id_pratica,)
    )]
    out["tariffe"] = [dict(r) for r in con.execute(
        "SELECT uid,pos,tipo_tariffa,valore,note FROM pratica_tariffe WHERE id_pratica=? ORDER BY pos, uid", (id_pratica,)
    )]
    out["attivita"] = [dict(r) for r in con.execute(
        "SELECT uid,pos,inizio,fine,descrizione,durata_min,tariffa_eur,tipo,note FROM attivita WHERE id_pratica=? ORDER BY pos, uid", (id_pratica,)
    )]
    out["scadenze"] = [dict(r) for r in con.execute(
        "SELECT uid,pos,data_scadenza,descrizione,note,completata FROM scadenze WHERE id_pratica=? ORDER BY pos, uid", (id_pratica,)
    )]
    out["documenti"] = [dict(r) for r in con.execute(
        "SELECT uid,pos,path,categoria,note,hash FROM documenti WHERE id_pratica=? ORDER BY pos, uid", (id_pratica,)
    )]
    return out

def export_pratica_sqlite(src_db_path: str, id_pratica: str, out_sqlite_path: str, schema_path: str = "db_schema.sql") -> str:
    """Crea un DB .sqlite contenente solo la pratica indicata (schema completo + righe correlate)."""
    # crea destinazione e schema
    initialize_schema(out_sqlite_path, schema_path=schema_path)
    with get_connection(src_db_path) as con_src, get_connection(out_sqlite_path) as con_dst:
        pratica = _fetch_pratica_as_dict(con_src, id_pratica)
        if not pratica:
            raise ValueError(f"Pratica non trovata: {id_pratica}")
        # upsert tramite repo_sqlite (riusa la logica delle child tables)
        repo_sqlite.upsert_pratica(con_dst, pratica)
    return out_sqlite_path

def import_pratica_sqlite(dest_db_path: str, pratica_sqlite_path: str, on_conflict: str = "upsert") -> str:
    """Importa una pratica da un file .sqlite; per ora supporta solo 'upsert'."""
    with get_connection(pratica_sqlite_path) as con_src:
        con_src.row_factory = sqlite3.Row
        row = con_src.execute("SELECT id_pratica FROM pratiche").fetchone()
        if not row:
            raise ValueError("Nessuna pratica nel file sorgente")
        pid = row["id_pratica"]
        pratica = _fetch_pratica_as_dict(con_src, pid)
    with get_connection(dest_db_path) as con_dst:
        repo_sqlite.upsert_pratica(con_dst, pratica)
    return pid
