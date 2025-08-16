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
from typing import Dict, Optional, Iterable, Any

from db_core import get_connection, atomic_tx


def upsert_pratica(pratica: Dict[str, Any], *, conn: Optional[Any] = None) -> None:
    """Insert or update a complete practice into the database.

    This function writes the core record to ``pratiche`` and then
    replaces all child collections (avvocati, tariffe, attivita,
    scadenze, documenti).  To preserve ordering, the ``ordine`` field
    from the tariff list is used as part of the composite key.

    Args:
        pratica: A dictionary representing the entire practice as used by
            the frontend and JSON backend.  Expected keys include
            ``id_pratica``, ``metadata``, ``avvocati``, ``tariffe``,
            ``attivita``, ``scadenze`` and ``documenti``.
        conn: Optional existing SQLite connection.  When omitted a
            temporary connection is created and closed automatically.

    Note:
        This implementation uses a simple delete/insert strategy for
        child collections.  For large practices consider batching
        deletes and inserts or diffing to reduce write amplification.
    """
    should_close = False
    if conn is None:
        conn = get_connection()
        should_close = True
    with atomic_tx(conn):
        meta = pratica.get('metadata', {})
        id_pratica = pratica['id_pratica']
        # Upsert core record
        conn.execute(
            """
            INSERT INTO pratiche (id_pratica, data_apertura, data_chiusura, tipo, settore,
                                  materia, referente, is_preventivo, note, created_at, updated_at)
            VALUES (:id_pratica, :data_apertura, :data_chiusura, :tipo, :settore,
                    :materia, :referente, :is_preventivo, :note, :created_at, :updated_at)
            ON CONFLICT(id_pratica) DO UPDATE SET
                data_apertura=excluded.data_apertura,
                data_chiusura=excluded.data_chiusura,
                tipo=excluded.tipo,
                settore=excluded.settore,
                materia=excluded.materia,
                referente=excluded.referente,
                is_preventivo=excluded.is_preventivo,
                note=excluded.note,
                updated_at=excluded.updated_at
            ;
            """,
            {
                'id_pratica': id_pratica,
                'data_apertura': meta.get('data_apertura'),
                'data_chiusura': meta.get('data_chiusura'),
                'tipo': meta.get('tipo'),
                'settore': meta.get('settore'),
                'materia': meta.get('materia'),
                'referente': meta.get('referente'),
                'is_preventivo': 1 if meta.get('is_preventivo') else 0,
                'note': meta.get('note'),
                'created_at': meta.get('created_at'),
                'updated_at': meta.get('updated_at') or meta.get('created_at'),
            }
        )
        # Upsert child lists via delete + insert
        conn.execute("DELETE FROM pratica_avvocati WHERE id_pratica = ?", (id_pratica,))
        for avv in pratica.get('avvocati', []):
            conn.execute(
                "INSERT INTO pratica_avvocati (id_pratica, ruolo, email, nome) VALUES (?,?,?,?)",
                (id_pratica, avv.get('ruolo'), avv.get('email'), avv.get('nome'))
            )
        conn.execute("DELETE FROM pratica_tariffe WHERE id_pratica = ?", (id_pratica,))
        for idx, tariffa in enumerate(pratica.get('tariffe', [])):
            conn.execute(
                "INSERT INTO pratica_tariffe (id_pratica, ordine, tipo_tariffa) VALUES (?,?,?)",
                (id_pratica, idx, tariffa.get('tipo'))
            )
        conn.execute("DELETE FROM attivita WHERE id_pratica = ?", (id_pratica,))
        for att in pratica.get('attivita', []):
            conn.execute(
                """
                INSERT INTO attivita (id_pratica, inizio, fine, descrizione, durata_min,
                                      tariffa_eur, tipo, note)
                VALUES (?,?,?,?,?,?,?,?)
                """,
                (id_pratica,
                 att.get('inizio'),
                 att.get('fine'),
                 att.get('descrizione'),
                 att.get('durata_min'),
                 att.get('tariffa_eur'),
                 att.get('tipo'),
                 att.get('note'))
            )
        conn.execute("DELETE FROM scadenze WHERE id_pratica = ?", (id_pratica,))
        for scad in pratica.get('scadenze', []):
            conn.execute(
                "INSERT INTO scadenze (id_pratica, data_scadenza, descrizione, note, completata) VALUES (?,?,?,?,?)",
                (id_pratica,
                 scad.get('data_scadenza'),
                 scad.get('descrizione'),
                 scad.get('note'),
                 1 if scad.get('completata') else 0)
            )
        conn.execute("DELETE FROM documenti WHERE id_pratica = ?", (id_pratica,))
        for doc in pratica.get('documenti', []):
            conn.execute(
                "INSERT INTO documenti (id_pratica, path, categoria, note, hash) VALUES (?,?,?,?,?)",
                (id_pratica,
                 doc.get('path'),
                 doc.get('categoria'),
                 doc.get('note'),
                 doc.get('hash'))
            )
    if should_close:
        conn.close()


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


def sync_lookups_from_json(lib_json_path: Optional[str] = None, *, conn: Optional[Any] = None) -> None:
    """Populate lookup tables from the JSON lookup files.

    This helper reads lookup files from ``lib_json`` (``materie.json``,
    ``settori.json``, ``tipo_pratica.json``, ``avvocati.json``) and
    populates the corresponding tables.  Existing entries are replaced.

    Args:
        lib_json_path: Path to the directory containing the lookup JSON
            files.  If omitted it defaults to ``lib_json`` relative to
            the project root.
        conn: Optional existing SQLite connection.
    """
    if lib_json_path is None:
        # Resolve relative to parent directory of this module
        lib_json_path = os.path.join(os.path.dirname(__file__), '..', 'lib_json')
    should_close = False
    if conn is None:
        conn = get_connection()
        should_close = True
    with atomic_tx(conn):
        # Clear existing lookup entries
        conn.execute("DELETE FROM lookup_tipi_pratica")
        conn.execute("DELETE FROM lookup_settori")
        conn.execute("DELETE FROM lookup_materie")
        conn.execute("DELETE FROM lookup_avvocati")
        # Load and insert each lookup file if it exists
        def load_json(name):
            path = os.path.join(lib_json_path, f"{name}.json")
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return []
        for item in load_json('tipo_pratica'):
            conn.execute(
                "INSERT INTO lookup_tipi_pratica (codice, descrizione) VALUES (?, ?)",
                (item.get('codice'), item.get('descrizione'))
            )
        for item in load_json('settori'):
            conn.execute(
                "INSERT INTO lookup_settori (codice, descrizione) VALUES (?, ?)",
                (item.get('codice'), item.get('descrizione'))
            )
        for item in load_json('materie'):
            conn.execute(
                "INSERT INTO lookup_materie (codice, descrizione) VALUES (?, ?)",
                (item.get('codice'), item.get('descrizione'))
            )
        for item in load_json('avvocati'):
            conn.execute(
                "INSERT INTO lookup_avvocati (email, nome, ruolo) VALUES (?, ?, ?)",
                (item.get('email'), item.get('nome'), item.get('ruolo'))
            )
    if should_close:
        conn.close()

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

