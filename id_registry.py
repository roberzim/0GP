# id_registry.py
from __future__ import annotations
from pathlib import Path
from datetime import date, datetime
from typing import Any, Dict, List, Tuple, Optional
import json, os, time
from contextlib import contextmanager

REG_PATH = Path('lib_json/id_pratiche.json')
LEGACY_SINGLE = Path('lib_json/id_pratica.json')   # v1/v2 (singolo oggetto)
LEGACY_LIST   = Path('lib_json/id_pratiche.json')  # v3 legacy (chiave "id_pratiche")

# ----------------- utili di base -----------------

def _now_iso() -> str:
    return datetime.now().isoformat(timespec='seconds')

def format_id(num: int, anno: int) -> str:
    return f"{int(num)}/{int(anno)}"

def parse_id(s: str) -> Tuple[int, int]:
    s = (s or '').strip()
    if '/' in s:
        a, b = s.split('/', 1)
        return int(a), int(b)
    raise ValueError(f"ID pratica non valido: {s!r}")

def make_file_link(path: str) -> str:
    """Costruisce un link file:// portabile (solo per UI, non viene salvato nel JSON)."""
    if not path:
        return ''
    p = Path(path).absolute().as_posix()
    return f"file:///{p.lstrip('/')}"

def _atomic_write(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + '.tmp')
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(text, encoding='utf-8')
    os.replace(tmp, path)

@contextmanager
def _lock(path: Path, timeout: float = 5.0, stale: float = 30.0):
    """File lock molto semplice per evitare scritture concorrenti."""
    lock = path.with_suffix(path.suffix + '.lock')
    start = time.monotonic()
    while lock.exists():
        try:
            if time.time() - lock.stat().st_mtime > stale:
                lock.unlink(missing_ok=True)
                break
        except Exception:
            pass
        if time.monotonic() - start > timeout:
            raise TimeoutError(f"Timeout lock su {path}")
        time.sleep(0.1)
    try:
        lock.write_text(f"{os.getpid()} @{time.time()}", encoding='utf-8')
        yield
    finally:
        try:
            lock.unlink()
        except Exception:
            pass

def _read() -> Dict[str, Any]:
    if REG_PATH.exists():
        try:
            return json.loads(REG_PATH.read_text(encoding='utf-8')) or {}
        except Exception:
            pass
    return {"version": 1, "records": []}

def _write(obj: Dict[str, Any]) -> None:
    with _lock(REG_PATH):
        _atomic_write(REG_PATH, json.dumps(obj, ensure_ascii=False, indent=2))

# ----------------- migrazione legacy (opzionale) -----------------

def migrate_legacy_if_needed() -> bool:
    """
    Se trova formati legacy li converte nello schema:
      {"version":1,"records":[{id_pratica,num_pratica,anno_pratica,nome_pratica,percorso_pratica,created_at,created_by?}]}
    Ritorna True se ha modificato qualcosa.
    """
    changed = False
    data = _read()
    records: List[Dict[str, Any]] = data.get('records', [])

    # v3 legacy: { "id_pratiche": [ ... ] }
    if LEGACY_LIST.exists():
        try:
            raw = json.loads(LEGACY_LIST.read_text(encoding='utf-8')) or {}
        except Exception:
            raw = {}
        if isinstance(raw, dict) and isinstance(raw.get('id_pratiche'), list):
            for r in raw['id_pratiche']:
                num  = int(r.get('num_pratica') or 0)
                anno = int(r.get('anno_pratica') or 0)
                if not (num and anno):
                    continue
                rec = {
                    "id_pratica": format_id(num, anno),
                    "num_pratica": num,
                    "anno_pratica": anno,
                    "nome_pratica": r.get("nome_pratica") or "",
                    "percorso_pratica": r.get("percorso_pratica") or r.get("link_percorso_pratica") or "",
                    "created_at": r.get("created_at") or _now_iso(),
                }
                if not any((x.get("id_pratica")==rec["id_pratica"] and x.get("percorso_pratica")==rec["percorso_pratica"]) for x in records):
                    records.append(rec)
                    changed = True

    # v1/v2 legacy: singolo contatore
    if LEGACY_SINGLE.exists():
        try:
            raw = json.loads(LEGACY_SINGLE.read_text(encoding='utf-8')) or {}
        except Exception:
            raw = {}
        if 'ultimo_numero' in raw or 'anno' in raw:  # v2
            # nulla da importare come record, ma utile per calcolo next id (ci pensiamo sotto)
            pass
        elif 'num_pratica' in raw or 'anno_pratica' in raw:  # v1
            pass

    if changed:
        data['version'] = 1
        data['records'] = records
        _write(data)
    return changed

# ----------------- API principali -----------------

def ensure_registry() -> None:
    """Crea il file se manca."""
    if not REG_PATH.exists():
        _write({"version": 1, "records": []})

def list_records(year: Optional[int] = None) -> List[Dict[str, Any]]:
    data = _read()
    recs: List[Dict[str, Any]] = data.get('records', [])
    if year is not None:
        recs = [r for r in recs if int(r.get('anno_pratica') or 0) == int(year)]
    # ordina per (anno,num) poi created_at
    recs.sort(key=lambda r: (int(r.get('anno_pratica') or 0), int(r.get('num_pratica') or 0), r.get('created_at') or ''))
    return recs

def find_record(id_pratica: str) -> Optional[Dict[str, Any]]:
    recs = _read().get('records', [])
    for r in recs:
        if (r.get('id_pratica') or '').strip() == (id_pratica or '').strip():
            return r
    return None

def load_next_id(today: date | None = None) -> Tuple[int, int]:
    """Ritorna (numero_proposto, anno_corrente) calcolando dai record esistenti."""
    today = today or date.today()
    data = _read()
    recs: List[Dict[str, Any]] = data.get("records", [])
    this_year = today.year
    nums = [int(r.get("num_pratica") or 0) for r in recs if int(r.get("anno_pratica") or 0) == this_year]
    next_num = (max(nums) + 1) if nums else 1

    # fallback: se non ci sono record, prova a leggere eventuali legacy contatori
    if not nums and LEGACY_SINGLE.exists():
        try:
            raw = json.loads(LEGACY_SINGLE.read_text(encoding='utf-8')) or {}
            if 'ultimo_numero' in raw and int(raw.get('anno') or this_year) == this_year:
                next_num = int(raw.get('ultimo_numero') or 0) + 1
            elif 'num_pratica' in raw and int(raw.get('anno_pratica') or this_year) == this_year:
                next_num = int(raw.get('num_pratica') or 0) + 1
        except Exception:
            pass

    return next_num, this_year

def persist_after_save(num: int, anno: int, nome: str, path: str, created_by: str | None = None) -> Dict[str, Any]:
    """Aggiunge un record al registro (non salva link file://, lo calcoli in UI)."""
    data = _read()
    rec = {
        "id_pratica": format_id(num, anno),
        "num_pratica": int(num),
        "anno_pratica": int(anno),
        "nome_pratica": nome or "",
        "percorso_pratica": path or "",
        "created_at": _now_iso(),
    }
    if created_by:
        rec["created_by"] = created_by
    data.setdefault("records", []).append(rec)
    _write(data)
    return rec

def update_record(id_pratica: str, **updates) -> Dict[str, Any]:
    """Aggiorna i campi di un record esistente (nome_pratica, percorso_pratica, created_by, ...)."""
    data = _read()
    recs: List[Dict[str, Any]] = data.get("records", [])
    for r in recs:
        if (r.get("id_pratica") or "") == id_pratica:
            r.update({k: v for k, v in updates.items() if k in {
                "nome_pratica", "percorso_pratica", "created_by"
            } and v is not None})
            _write(data)
            return r
    raise KeyError(f"Record {id_pratica!r} non trovato")

def delete_record(id_pratica: str) -> bool:
    """Elimina un record. Ritorna True se eliminato."""
    data = _read()
    recs: List[Dict[str, Any]] = data.get("records", [])
    new_recs = [r for r in recs if (r.get("id_pratica") or "") != id_pratica]
    if len(new_recs) != len(recs):
        data["records"] = new_recs
        _write(data)
        return True
    return False

