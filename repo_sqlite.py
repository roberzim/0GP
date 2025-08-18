from __future__ import annotations

import os, json, sqlite3
from typing import Any, Dict, List, Optional, Iterable, Tuple
from contextlib import contextmanager
from db_core import get_connection as _get_connection, atomic_tx

DB_PATH = os.environ.get('GP_DB_PATH', os.path.join('archivio', '0gp.sqlite'))

# ---- Connection helper -------------------------------------------------------
@contextmanager
def get_connection(db_path: Optional[str] = None):
    """Context manager per una connessione pronta all'uso."""
    with _get_connection(db_path or DB_PATH) as con:
        try:
            con.row_factory = sqlite3.Row
        except Exception:
            pass
        yield con

# ---- Utilities ---------------------------------------------------------------
def _ensure_uid(item: Dict[str, Any]) -> str:
    u = (item.get("uid") or "").strip()
    if u:
        return u
    import uuid
    u = uuid.uuid4().hex
    item["uid"] = u
    return u

def _table_columns(con: sqlite3.Connection, table: str) -> set:
    try:
        return {r[1] for r in con.execute(f"PRAGMA table_info({table})")}
    except Exception:
        return set()

def _row_to_dict(r: sqlite3.Row) -> Dict[str, Any]:
    return {k: r[k] for k in r.keys()}

# ---- Generic child merge (1->N) ---------------------------------------------
def merge_children(
    con: sqlite3.Connection, *,
    table: str, parent_col: str, parent_id: str,
    rows: List[Dict[str, Any]],
    colmap: Dict[str, str],
    order_field: str = "pos",
    delete_missing: bool = True,
) -> None:
    """
    Merge incrementale di una tabella figlia, basato su uid. Filtra automaticamente
    i campi che non esistono nella tabella (evita errori 'no such column').
    """
    tcols = _table_columns(con, table)

    # scegli la colonna di ordinamento realmente esistente
    if order_field not in tcols:
        order_field = "pos" if "pos" in tcols else ("ordine" if "ordine" in tcols else None)

    # snapshot uids esistenti
    existing = {u for (u,) in con.execute(f"SELECT uid FROM {table} WHERE {parent_col}=?", (parent_id,))}
    incoming_uids = set()

    # upsert/insert
    for i, item in enumerate(rows or []):
        uid = _ensure_uid(item); incoming_uids.add(uid)

        cols: List[str] = [parent_col, "uid"]
        vals: List[Any] = [parent_id, uid]

        # order
        if order_field:
            cols.append(order_field)
            vals.append(item.get(order_field, i))  # rispetta pos/ordine se fornito

        # mappa campi UI -> colonne DB, filtrate
        for src, col in (colmap or {}).items():
            if col in tcols:
                cols.append(col)
                vals.append(item.get(src))

        if uid in existing:
            set_list = [f"{c}=?" for c in cols if c not in (parent_col, "uid")]
            where_vals = [v for c, v in zip(cols, vals) if c not in (parent_col, "uid")]
            con.execute(
                f"UPDATE {table} SET {', '.join(set_list)} WHERE {parent_col}=? AND uid=?",
                where_vals + [parent_id, uid],
            )
        else:
            placeholders = ",".join("?" for _ in cols)
            con.execute(f"INSERT INTO {table}({', '.join(cols)}) VALUES({placeholders})", vals)

    # delete righe non più presenti
    if delete_missing:
        to_delete = existing - incoming_uids
        if to_delete:
            con.executemany(
                f"DELETE FROM {table} WHERE {parent_col}=? AND uid=?",
                [(parent_id, u) for u in to_delete],
            )

# ---- Upsert pratica ----------------------------------------------------------
def upsert_pratica(con: sqlite3.Connection, pratica: Dict[str, Any]) -> None:
    pid = pratica.get('id_pratica') or pratica.get('id') or pratica.get('codice')
    if not pid:
        raise ValueError('pratica senza id_pratica')

    anno = pratica.get('anno'); numero = pratica.get('numero')
    tipo = pratica.get('tipo_pratica') or pratica.get('tipo')
    settore = pratica.get('settore'); materia = pratica.get('materia')
    ref_email = pratica.get('referente_email'); ref_nome = pratica.get('referente_nome')
    preventivo = 1 if pratica.get('preventivo') else 0
    note = pratica.get('note')
    raw = json.dumps(pratica, ensure_ascii=False)

    with atomic_tx(con):
        con.execute("""
            INSERT INTO pratiche
              (id_pratica, anno, numero, tipo_pratica, settore, materia,
               referente_email, referente_nome, preventivo, note, updated_at, raw_json)
            VALUES (?,?,?,?,?,?,?,?,?,?,datetime('now'),?)
            ON CONFLICT(id_pratica) DO UPDATE SET
              anno=excluded.anno, numero=excluded.numero, tipo_pratica=excluded.tipo_pratica,
              settore=excluded.settore, materia=excluded.materia,
              referente_email=excluded.referente_email, referente_nome=excluded.referente_nome,
              preventivo=excluded.preventivo, note=excluded.note,
              updated_at=datetime('now'), raw_json=excluded.raw_json
        """, (pid, anno, numero, tipo, settore, materia, ref_email, ref_nome, preventivo, note, raw))

        # Avvocati
        avv = pratica.get('avvocati') or pratica.get('pratica_avvocati') or []
        merge_children(
            con, table="pratica_avvocati", parent_col="id_pratica", parent_id=pid,
            rows=avv, colmap={"email":"email","nome":"nome","ruolo":"ruolo"}, order_field="pos"
        )

        # Tariffe (schema tipico: id_pratica, uid, pos, ordine)
        tar = pratica.get('tariffe') or pratica.get('pratica_tariffe') or []
        merge_children(
            con, table="pratica_tariffe", parent_col="id_pratica", parent_id=pid,
            rows=tar, colmap={"valore":"valore","note":"note","tipo_tariffa":"tipo_tariffa"}, order_field="pos"
        )

        # Attività
        att = pratica.get('attivita') or pratica.get('attività') or []
        merge_children(
            con, table="attivita", parent_col="id_pratica", parent_id=pid,
            rows=att, colmap={"inizio":"inizio","fine":"fine","descrizione":"descrizione",
                              "durata_min":"durata_min","tariffa_eur":"tariffa_eur",
                              "tipo":"tipo","note":"note"}, order_field="pos"
        )

        # Scadenze
        scad = pratica.get('scadenze') or []
        merge_children(
            con, table="scadenze", parent_col="id_pratica", parent_id=pid,
            rows=scad, colmap={"data_scadenza":"data_scadenza","descrizione":"descrizione",
                               "note":"note","completata":"completata"}, order_field="pos"
        )

        # Documenti
        doc = pratica.get('documenti') or []
        merge_children(
            con, table="documenti", parent_col="id_pratica", parent_id=pid,
            rows=doc, colmap={"path":"path","categoria":"categoria","note":"note","hash":"hash"}, order_field="pos"
        )

# ---- Load pratica (flessibile) ----------------------------------------------
def _load_pratica_using_con(con: sqlite3.Connection, id_pratica: str) -> Optional[Dict[str, Any]]:
    con.row_factory = sqlite3.Row
    row = con.execute("SELECT * FROM pratiche WHERE id_pratica = ?", (id_pratica,)).fetchone()
    if not row:
        return None

    # Se c’è uno snapshot JSON, usalo come base
    base: Dict[str, Any]
    raw = row["raw_json"] if "raw_json" in row.keys() else None
    if raw:
        try:
            base = json.loads(raw)
            base["id_pratica"] = row["id_pratica"]
        except Exception:
            base = {"id_pratica": row["id_pratica"]}
    else:
        base = {"id_pratica": row["id_pratica"]}

    # campi noti della tabella pratiche
    for k in ("anno","numero","tipo_pratica","settore","materia",
              "referente_email","referente_nome","preventivo","note",
              "created_at","updated_at"):
        if k in row.keys():
            base[k] = row[k]

    # figli
    def fetch(table: str) -> List[Dict[str, Any]]:
        tcols = _table_columns(con, table)
        order_by = "pos" if "pos" in tcols else ("ordine" if "ordine" in tcols else None)
        q = f"SELECT * FROM {table} WHERE id_pratica=?"
        if order_by:
            q += f" ORDER BY COALESCE({order_by},0)"
        return [_row_to_dict(r) for r in con.execute(q, (id_pratica,)).fetchall()]

    base["avvocati"] = fetch("pratica_avvocati")
    base["tariffe"]  = fetch("pratica_tariffe")
    base["attivita"] = fetch("attivita")
    base["scadenze"] = fetch("scadenze")
    base["documenti"]= fetch("documenti")
    return base

def load_pratica(*args, **kwargs) -> Optional[Dict[str, Any]]:
    """
    Uso flessibile:
      - load_pratica(id_pratica, conn=CONN)
      - load_pratica(id_pratica)  (usa DB_PATH)
      - load_pratica(DB_PATH, id_pratica)  (compat per chiamate legacy)
    """
    if len(args) == 1:
        # (id_pratica) oppure (db_path, con=...)
        id_or_path = args[0]
        conn = kwargs.get("conn")
        if isinstance(conn, sqlite3.Connection):
            return _load_pratica_using_con(conn, id_or_path)
        with get_connection(kwargs.get("db_path") or DB_PATH) as con:
            return _load_pratica_using_con(con, id_or_path)
    elif len(args) == 2:
        # (db_path, id_pratica)
        db_path, pid = args
        with get_connection(db_path) as con:
            return _load_pratica_using_con(con, pid)
    else:
        # firma esplicita: (id_pratica, conn=...)
        pid = kwargs.get("id_pratica")
        conn = kwargs.get("conn")
        if not pid:
            return None
        if isinstance(conn, sqlite3.Connection):
            return _load_pratica_using_con(conn, pid)
        with get_connection(kwargs.get("db_path") or DB_PATH) as con:
            return _load_pratica_using_con(con, pid)

# ---- Lookups -----------------------------------------------------------------
def sync_lookups_from_json(con: sqlite3.Connection, lib_json_dir: str) -> None:
    """Popola le lookup da JSON (stringhe/list/dict)."""
    import os, json
    def load_json(name: str):
        p = os.path.join(lib_json_dir, name if name.endswith(".json") else f"{name}.json")
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        return None

    def to_code_label(data) -> List[Tuple[str,str]]:
        out: List[Tuple[str,str]] = []
        if not data: return out
        if isinstance(data, list):
            for x in data:
                if isinstance(x, str):
                    out.append((x, x))
                elif isinstance(x, dict):
                    code = x.get('codice') or x.get('id') or x.get('value') or x.get('code') or x.get('key')
                    label= x.get('label')  or x.get('nome') or x.get('name')  or x.get('descrizione') or code
                    if code:
                        out.append((str(code), str(label or code)))
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

    with atomic_tx(con):
        con.execute('DELETE FROM lookup_tipi_pratica')
        con.execute('DELETE FROM lookup_settori')
        con.execute('DELETE FROM lookup_materie')
        con.execute('DELETE FROM lookup_avvocati')

        tipi = to_code_label(load_json('tipo_pratica'))
        sett = to_code_label(load_json('settori'))
        mate = to_code_label(load_json('materie'))
        if tipi: con.executemany('INSERT OR IGNORE INTO lookup_tipi_pratica(codice,label) VALUES(?,?)', tipi)
        if sett: con.executemany('INSERT OR IGNORE INTO lookup_settori(codice,label) VALUES(?,?)', sett)
        if mate: con.executemany('INSERT OR IGNORE INTO lookup_materie(codice,label) VALUES(?,?)', mate)

        avv = load_json('avvocati'); rows = []
        if isinstance(avv, list):
            for x in avv:
                if isinstance(x, dict):
                    email = x.get('email') or x.get('mail') or x.get('id')
                    nome  = x.get('nome')  or x.get('name') or x.get('label') or email
                    if email: rows.append((str(email), str(nome)))
        elif isinstance(avv, dict):
            for email, v in avv.items():
                if isinstance(v, str): rows.append((str(email), v))
                elif isinstance(v, dict):
                    nome = v.get('nome') or v.get('name') or v.get('label') or email
                    rows.append((str(email), str(nome)))
        if rows:
            con.executemany('INSERT OR REPLACE INTO lookup_avvocati(email,nome) VALUES(?,?)', rows)

# ---- Ingest archivio JSON (opzionale) ---------------------------------------
def ingest_archive_from_json(con: sqlite3.Connection, app_pratiche_dir: str) -> int:
    """Importa pratiche *.json da una cartella e fa upsert sul DB."""
    import os, re
    count = 0
    if not os.path.isdir(app_pratiche_dir):
        return 0
    def _get(d,*names,default=None):
        for n in names:
            if n in d: return d[n]
        return default
    for root, _, files in os.walk(app_pratiche_dir):
        candidates = [f for f in files if f.endswith('.json') and ('pratica' in f or re.search(r'\d+_\d+\.json$', f))]
        for f in candidates:
            p = os.path.join(root, f)
            try:
                data = json.load(open(p, 'r', encoding='utf-8'))
                pid = _get(data, 'id_pratica', 'id', 'codice')
                if not pid: continue
                upsert_pratica(con, data)
                count += 1
            except Exception:
                continue
    return count
