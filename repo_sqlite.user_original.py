"""
repo_sqlite.py
----------------

High‑level data access layer for the SQLite backend.  This module exposes
functions for loading and saving practices in their structured form.  It
mirrors the interface of the existing JSON repository (`repo.py`) but
persists data to a relational database instead.  Each function accepts
an optional SQLite connection; if none is provided a new connection
connected to the default database is created and closed automatically.

The primary entry point is :func:`upsert_pratica`, which takes a
dictionary representing a complete practice (matching the structure
produced by the NiceGUI frontend) and persists it across all relevant
tables.  The companion :func:`load_pratica` reconstructs a practice
dictionary from the database.

Note that lookups remain primarily maintained in JSON files but can be
cached in the database via :func:`sync_lookups_from_json` to simplify
queries.
"""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from db_core import get_connection as _get_connection, atomic_tx
from typing import Any, Dict, List, Tuple
from db_core import atomic_tx

DB_PATH = os.environ.get('GP_DB_PATH', os.path.join('archivio', '0gp.sqlite'))

@contextmanager
def get_connection():
    """Wrapper: restituisce una connessione pronta all'uso al DB predefinito."""
    with _get_connection(DB_PATH) as con:
        yield con


def _ensure_uid(item: Dict[str, Any]) -> str:
    u = (item.get("uid") or "").strip()
    if u: 
        return u
    # se l'UI non fornisce uid, ne creiamo uno (meglio farlo in UI!)
    import uuid
    u = uuid.uuid4().hex
    item["uid"] = u
    return u

def merge_children(con, *, table: str, parent_col: str, parent_id: str,
                   rows: List[Dict[str, Any]], colmap: Dict[str,str],
                   order_field: str = "pos", delete_missing: bool = True) -> None:
    """
    Merge incrementale di una tabella figlia (1→N) basato su uid.
    - colmap: mappa {campo_UI: colonna_DB}
    - rows devono contenere 'uid' stabile. Se manca lo generiamo (consigliato averlo in UI).
    """
    # 1) snapshot uids esistenti
    existing = { r[0] for r in con.execute(f"SELECT uid FROM {table} WHERE {parent_col}=?", (parent_id,)) }
    incoming_uids = set()

    # 2) upsert/insert
    for i, item in enumerate(rows or []):
        uid = _ensure_uid(item)
        incoming_uids.add(uid)
        # costruisci coppie (colonna, valore)
        cols = [parent_col, "uid", order_field]
        vals = [parent_id, uid, i]
        for src, col in colmap.items():
            cols.append(col)
            vals.append(item.get(src))
        if uid in existing:
            # UPDATE
            set_list = [f"{c}=?" for c in cols[2:]]  # non cambiamo parent_col, uid
            con.execute(f"UPDATE {table} SET {', '.join(set_list)} WHERE {parent_col}=? AND uid=?",
                        vals[2:] + [parent_id, uid])
        else:
            # INSERT
            placeholders = ",".join("?" for _ in cols)
            con.execute(f"INSERT INTO {table}({', '.join(cols)}) VALUES({placeholders})", vals)

    # 3) delete righe sparite (se richiesto)
    if delete_missing:
        to_delete = existing - incoming_uids
        if to_delete:
            con.executemany(f"DELETE FROM {table} WHERE {parent_col}=? AND uid=?",
                            [(parent_id, u) for u in to_delete])




def upsert_pratica(con, pratica: Dict[str, Any]) -> None:
    pid = pratica.get('id_pratica') or pratica.get('id') or pratica.get('codice')
    if not pid:
        raise ValueError('pratica senza id_pratica')

    anno = pratica.get('anno'); numero = pratica.get('numero')
    tipo = pratica.get('tipo_pratica') or pratica.get('tipo')
    settore = pratica.get('settore'); materia = pratica.get('materia')
    ref_email = pratica.get('referente_email'); ref_nome = pratica.get('referente_nome')
    preventivo = 1 if pratica.get('preventivo') else 0
    note = pratica.get('note')
    import json as _json
    raw = _json.dumps(pratica, ensure_ascii=False)

    with atomic_tx(con):
        # master
        con.execute("""
            INSERT INTO pratiche
              (id_pratica, anno, numero, tipo_pratica, settore, materia, referente_email, referente_nome, preventivo, note, updated_at, raw_json)
            VALUES (?,?,?,?,?,?,?,?,?,?,datetime('now'),?)
            ON CONFLICT(id_pratica) DO UPDATE SET
              anno=excluded.anno, numero=excluded.numero, tipo_pratica=excluded.tipo_pratica,
              settore=excluded.settore, materia=excluded.materia,
              referente_email=excluded.referente_email, referente_nome=excluded.referente_nome,
              preventivo=excluded.preventivo, note=excluded.note,
              updated_at=datetime('now'), raw_json=excluded.raw_json
        """, (pid, anno, numero, tipo, settore, materia, ref_email, ref_nome, preventivo, note, raw))

        # avvocati (consigliato: avere 'uid' lato UI; se manca usiamo email+ruolo implicitamente stabili)
        avv = pratica.get('avvocati') or pratica.get('pratica_avvocati') or []
        if avv and any('uid' in x for x in avv):
            merge_children(con,
                table="pratica_avvocati", parent_col="id_pratica", parent_id=pid,
                rows=avv,
                colmap={"email":"email","nome":"nome","ruolo":"ruolo"},
                order_field="pos"
            )
        else:
            # fallback robusto su email+ruolo (mantiene stabilità senza uid)
            con.execute("DELETE FROM pratica_avvocati WHERE id_pratica=?", (pid,))
            for i, a in enumerate(avv):
                con.execute("""INSERT INTO pratica_avvocati(id_pratica,uid,pos,email,nome,ruolo)
                               VALUES(?,?,?,?,?,?)""",
                            (pid, a.get('uid') or f"{a.get('email','')}|{a.get('ruolo','')}", i, a.get('email'), a.get('nome'), a.get('ruolo')))

        # tariffe
        merge_children(con,
            table="pratica_tariffe", parent_col="id_pratica", parent_id=pid,
            rows=pratica.get('tariffe') or pratica.get('pratica_tariffe') or [],
            colmap={"tipo_tariffa":"tipo_tariffa","valore":"valore","note":"note"},
            order_field="pos"
        )

        # attività
        merge_children(con,
            table="attivita", parent_col="id_pratica", parent_id=pid,
            rows=pratica.get('attivita') or pratica.get('attività') or [],
            colmap={"inizio":"inizio","fine":"fine","descrizione":"descrizione","durata_min":"durata_min","tariffa_eur":"tariffa_eur","tipo":"tipo","note":"note"},
            order_field="pos"
        )

        # scadenze
        merge_children(con,
            table="scadenze", parent_col="id_pratica", parent_id=pid,
            rows=pratica.get('scadenze') or [],
            colmap={"data_scadenza":"data_scadenza","descrizione":"descrizione","note":"note","completata":"completata"},
            order_field="pos"
        )

        # documenti
        merge_children(con,
            table="documenti", parent_col="id_pratica", parent_id=pid,
            rows=pratica.get('documenti') or [],
            colmap={"path":"path","categoria":"categoria","note":"note","hash":"hash"},
            order_field="pos"
        )


def load_pratica(id_pratica: str, *, conn: Optional[Any] = None) -> Optional[Dict[str, Any]]:
    """Load a practice from the database and reconstruct its nested structure.

    Args:
        id_pratica: Natural identifier of the practice (e.g. "8_2025").
        conn: Optional existing SQLite connection.

    Returns:
        A dictionary matching the JSON structure used by the application,
        or ``None`` if the practice does not exist.
    """
    should_close = False
    if conn is None:
        conn = get_connection()
        should_close = True
    cur = conn.cursor()
    row = cur.execute("SELECT * FROM pratiche WHERE id_pratica = ?", (id_pratica,)).fetchone()
    if row is None:
        if should_close:
            conn.close()
        return None
    pratica = {
        'id_pratica': row['id_pratica'],
        'metadata': {
            'data_apertura': row['data_apertura'],
            'data_chiusura': row['data_chiusura'],
            'tipo': row['tipo'],
            'settore': row['settore'],
            'materia': row['materia'],
            'referente': row['referente'],
            'is_preventivo': bool(row['is_preventivo']),
            'note': row['note'],
            'created_at': row['created_at'],
            'updated_at': row['updated_at'],
        },
        'avvocati': [],
        'tariffe': [],
        'attivita': [],
        'scadenze': [],
        'documenti': [],
    }
    for avv in cur.execute("SELECT ruolo, email, nome FROM pratica_avvocati WHERE id_pratica = ?", (id_pratica,)):
        pratica['avvocati'].append({'ruolo': avv['ruolo'], 'email': avv['email'], 'nome': avv['nome']})
    for tariffa in cur.execute("SELECT ordine, tipo_tariffa FROM pratica_tariffe WHERE id_pratica = ? ORDER BY ordine", (id_pratica,)):
        pratica['tariffe'].append({'ordine': tariffa['ordine'], 'tipo': tariffa['tipo_tariffa']})
    for att in cur.execute("SELECT * FROM attivita WHERE id_pratica = ?", (id_pratica,)):
        pratica['attivita'].append({
            'id': att['id'],
            'inizio': att['inizio'],
            'fine': att['fine'],
            'descrizione': att['descrizione'],
            'durata_min': att['durata_min'],
            'tariffa_eur': att['tariffa_eur'],
            'tipo': att['tipo'],
            'note': att['note'],
        })
    for scad in cur.execute("SELECT * FROM scadenze WHERE id_pratica = ?", (id_pratica,)):
        pratica['scadenze'].append({
            'id': scad['id'],
            'data_scadenza': scad['data_scadenza'],
            'descrizione': scad['descrizione'],
            'note': scad['note'],
            'completata': bool(scad['completata']),
        })
    for doc in cur.execute("SELECT * FROM documenti WHERE id_pratica = ?", (id_pratica,)):
        pratica['documenti'].append({
            'id': doc['id'],
            'path': doc['path'],
            'categoria': doc['categoria'],
            'note': doc['note'],
            'hash': doc['hash'],
        })
    if should_close:
        conn.close()
    return pratica


def sync_lookups_from_json(lib_json_path: Optional[str] = None, *, con: Optional[Any] = None, db_path: Optional[str] = None) -> None:
    """
    Popola le tabelle di lookup da lib_json.
    Scrive su:
      lookup_tipi_pratica(codice,label),
      lookup_settori(codice,label),
      lookup_materie(codice,label),
      lookup_avvocati(email,nome).
    Accetta formati JSON eterogenei (liste di stringhe, liste di dict, dict-mappa).
    """
    import json, os
    from pathlib import Path
    from db_core import get_connection as _get_connection, atomic_tx

    # risolvi cartella lib_json
    if lib_json_path is None:
        lib_json_path = os.environ.get('GP_LIB_JSON', str(Path(__file__).resolve().parent.parent / 'lib_json'))
    lib = Path(lib_json_path)

    def load_json(name: str):
        p = lib / f'{name}.json'
        if p.exists():
            with p.open('r', encoding='utf-8') as f:
                return json.load(f)
        return None

    def normalize_code_label(data):
        out = []
        if data is None: 
            return out
        if isinstance(data, list):
            for x in data:
                if isinstance(x, str):
                    out.append((x, x))
                elif isinstance(x, dict):
                    code = x.get('codice') or x.get('id') or x.get('value') or x.get('code') or x.get('key')
                    label= x.get('label')  or x.get('nome') or x.get('name')  or x.get('descrizione') or code
                    if code:
                        out.append((str(code), str(label) if label is not None else str(code)))
        elif isinstance(data, dict):
            for k, v in data.items():
                if isinstance(v, str):
                    out.append((str(k), v))
                elif isinstance(v, dict):
                    label = v.get('label') or v.get('nome') or v.get('name') or str(k)
                    out.append((str(k), str(label)))
                else:
                    out.append((str(k), str(v)))
        return out

    must_close = False
    if con is None:
        if db_path is None:
            db_path = os.environ.get('GP_DB_PATH', os.path.join('archivio','0gp.sqlite'))
        cm = _get_connection(db_path)
        con = cm.__enter__()
        must_close = True

    try:
        with atomic_tx(con):
            con.execute('DELETE FROM lookup_tipi_pratica')
            con.execute('DELETE FROM lookup_settori')
            con.execute('DELETE FROM lookup_materie')
            con.execute('DELETE FROM lookup_avvocati')

            tipi = normalize_code_label(load_json('tipo_pratica'))
            if tipi:
                con.executemany('INSERT OR IGNORE INTO lookup_tipi_pratica(codice,label) VALUES(?,?)', tipi)

            sett = normalize_code_label(load_json('settori'))
            if sett:
                con.executemany('INSERT OR IGNORE INTO lookup_settori(codice,label) VALUES(?,?)', sett)

            mate = normalize_code_label(load_json('materie'))
            if mate:
                con.executemany('INSERT OR IGNORE INTO lookup_materie(codice,label) VALUES(?,?)', mate)

            avv = load_json('avvocati')
            rows = []
            if isinstance(avv, list):
                for x in avv:
                    if isinstance(x, dict):
                        email = x.get('email') or x.get('mail') or x.get('id')
                        nome  = x.get('nome')  or x.get('name') or x.get('label') or email
                        if email:
                            rows.append((str(email), str(nome)))
            elif isinstance(avv, dict):
                for email, v in avv.items():
                    if isinstance(v, str):
                        rows.append((str(email), v))
                    elif isinstance(v, dict):
                        nome = v.get('nome') or v.get('name') or v.get('label') or email
                        rows.append((str(email), str(nome)))
            if rows:
                con.executemany('INSERT OR REPLACE INTO lookup_avvocati(email,nome) VALUES(?,?)', rows)
    finally:
        if must_close:
            cm.__exit__(None, None, None)



def ingest_archive_from_json(con, app_pratiche_dir: str) -> int:
    import os, json, re
    count = 0
    if not os.path.isdir(app_pratiche_dir):
        return 0
    def _get(d,*names,default=None):
        for n in names:
            if n in d: return d[n]
        return default
    from repo_sqlite import upsert_pratica  # se è nello stesso file, puoi chiamare direttamente upsert_pratica
    for root, dirs, files in os.walk(app_pratiche_dir):
        candidates = [f for f in files if f.endswith('.json') and ('pratica' in f or re.search(r'\\d+_\\d+\\.json$', f))]
        for f in candidates:
            p = os.path.join(root, f)
            try:
                data = json.load(open(p, 'r', encoding='utf-8'))
                pid = _get(data, 'id_pratica', 'id', 'codice')
                if not pid:
                    continue
                upsert_pratica(con, data)
                count += 1
            except Exception:
                continue
    return count

# --- sostituisci in repo_sqlite.py ---
def sync_lookups_from_json(con, lib_json_dir: str) -> None:
    import os, json

    def load_json(name):
        p = os.path.join(lib_json_dir, name)
        if os.path.exists(p):
            with open(p, 'r', encoding='utf-8') as f:
                return json.load(f)
        return None

    def normalize_code_label(data):
        """
        Accetta:
        - lista di stringhe -> (stringa, stringa)
        - lista di dict      -> (codice/id/value/key, label/nome/name/descrizione)
        - dict mappa         -> (chiave, valore o valore['label'|'nome'|'name'])
        Ritorna lista di tuple (codice, label) senza None.
        """
        out = []
        if isinstance(data, list):
            for x in data:
                if isinstance(x, str):
                    out.append((x, x))
                elif isinstance(x, dict):
                    code = x.get('codice') or x.get('id') or x.get('value') or x.get('code') or x.get('key')
                    label = x.get('label') or x.get('nome') or x.get('name') or x.get('descrizione') or code
                    if code:
                        out.append((code, label))
        elif isinstance(data, dict):
            for k, v in data.items():
                if isinstance(v, str):
                    out.append((k, v))
                elif isinstance(v, dict):
                    label = v.get('label') or v.get('nome') or v.get('name') or k
                    out.append((k, label))
                else:
                    out.append((k, str(v)))
        return out

    # Tipi / Settori / Materie
    tipi = normalize_code_label(load_json('tipo_pratica.json') or [])
    sett = normalize_code_label(load_json('settori.json') or [])
    mate = normalize_code_label(load_json('materie.json') or [])

    con.execute('DELETE FROM lookup_tipi_pratica')
    con.execute('DELETE FROM lookup_settori')
    con.execute('DELETE FROM lookup_materie')

    if tipi:
        con.executemany("INSERT OR IGNORE INTO lookup_tipi_pratica(codice,label) VALUES(?,?)", tipi)
    if sett:
        con.executemany("INSERT OR IGNORE INTO lookup_settori(codice,label) VALUES(?,?)", sett)
    if mate:
        con.executemany("INSERT OR IGNORE INTO lookup_materie(codice,label) VALUES(?,?)", mate)

    # Avvocati: supporta sia lista di dict che dict mappa email->nome
    avv_data = load_json('avvocati.json') or []
    rows = []
    if isinstance(avv_data, list):
        for x in avv_data:
            if isinstance(x, dict):
                email = x.get('email') or x.get('mail') or x.get('id')
                nome  = x.get('nome') or x.get('name') or x.get('label') or email
                if email:
                    rows.append((email, nome))
            elif isinstance(x, str):
                # Se è solo una stringa e non abbiamo email, saltiamo (PK = email)
                # In alternativa potresti generare una email fittizia, ma sconsiglio.
                continue
    elif isinstance(avv_data, dict):
        for email, v in avv_data.items():
            if isinstance(v, str):
                rows.append((email, v))
            elif isinstance(v, dict):
                nome = v.get('nome') or v.get('name') or v.get('label') or email
                rows.append((email, nome))

    con.execute('DELETE FROM lookup_avvocati')
    if rows:
        con.executemany("INSERT OR REPLACE INTO lookup_avvocati(email,nome) VALUES(?,?)", rows)

