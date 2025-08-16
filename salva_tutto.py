# salva_tutto.py — versione JSON-only (patch dual-save conforme requisiti)
from __future__ import annotations
import os, json, time
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, Optional
from contextlib import contextmanager
from nicegui import ui
from history import append_history
from reindex import reindex  # reindex post-salvataggio
from dual_save import dual_save
import re

# ----------------- util -----------------

def _txt(v: Any) -> str:
    return '' if v is None else str(v).strip()

def _sel_value(x):
    """Accetta sia widget .value che stringhe."""
    try:
        return _txt(getattr(x, 'value'))
    except Exception:
        return _txt(x)

def _safe_filename_from_id(id_pratica: str) -> str:
    id_pratica = _txt(id_pratica)
    if '/' in id_pratica:
        num, anno = id_pratica.split('/', 1)
    else:
        parts = id_pratica.split()
        num, anno = (parts[0], parts[1]) if len(parts) >= 2 else (id_pratica, '')
    return f"{num.strip()}_{anno.strip()}".strip('_')

def _append_logs(pratica_path: str, msg: str) -> None:
    when = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f"[{when}] {msg}\n"
    try:
        os.makedirs('logs', exist_ok=True)
        with open(os.path.join('logs', 'log_gestione_pratica'), 'a', encoding='utf-8') as f:
            f.write(line)
    except Exception:
        pass
    try:
        lp_dir = os.path.join(pratica_path, 'log_pratica')
        os.makedirs(lp_dir, exist_ok=True)
        with open(os.path.join(lp_dir, 'log.txt'), 'a', encoding='utf-8') as f:
            f.write(line)
    except Exception:
        pass

def _atomic_write_text(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(text, encoding='utf-8')
    os.replace(tmp, path)

@contextmanager
def _lock(path: Path, timeout: float = 10.0, stale: float = 30.0):
    """File lock semplice con TTL per evitare scritture concorrenti."""
    lock = path.with_suffix('.lock')
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
        lock.write_text(f"{os.getpid()} @ {time.time()}", encoding='utf-8')
        yield
    finally:
        try:
            lock.unlink()
        except Exception:
            pass

def _read_existing(p: Path) -> Optional[Dict[str, Any]]:
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding='utf-8'))
    except Exception:
        return None

# ----------------- somme/format -----------------

def _parse_euro(v) -> float:
    if v is None:
        return 0.0
    s = str(v).strip().replace('€', '').replace(' ', '')
    if ',' in s and '.' in s:
        s = s.replace('.', '').replace(',', '.')
    else:
        s = s.replace(',', '.')
    try:
        return float(s)
    except Exception:
        return 0.0

def _somma_tariffe_sezione(pratica_data: Dict[str, Any], sezione: str) -> float:
    key = f"tariffe_{sezione}"
    totale = 0.0
    blocco = pratica_data.get(key, {}) or {}
    if isinstance(blocco, dict):
        for _tipo, righe in blocco.items():
            for r in (righe or []):
                totale += _parse_euro((r or {}).get('tot'))
    return totale

def _somma_tabelle_sezione(pratica_data: Dict[str, Any], sezione: str) -> float:
    key = 'preventivi' if sezione == 'contenzioso' else 'preventivi_stragiudiziale'
    totale = 0.0
    blocco = pratica_data.get(key, {}) or {}
    if isinstance(blocco, dict):
        for _n, obj in blocco.items():
            dati = (obj or {}).get('dati', {}) or {}
            totale += _parse_euro(dati.get('totale_documento'))
    return totale

# ----------------- build record JSON -----------------

def _build_record(pratica_data: Dict[str, Any], anagrafica_data: Dict[str, Any]) -> Dict[str, Any]:
    tipo_tariffe = []
    for t in (pratica_data.get('tipo_tariffe') or []):
        v = _sel_value(t)
        if v:
            tipo_tariffe.append(v)

    avv_ref = pratica_data.get('avvocato_referente') or pratica_data.get('avv_referente')
    avv_mand = pratica_data.get('avvocato_in_mandato') or pratica_data.get('avv_mandato') or []

    record: Dict[str, Any] = {
        'id_pratica': _txt(pratica_data.get('id_pratica')),
        'nome_pratica': _txt(pratica_data.get('nome_pratica')),
        'percorso_pratica': _txt(pratica_data.get('percorso_pratica')),
        'data_apertura': _txt(pratica_data.get('data_apertura')),
        'data_chiusura': _txt(pratica_data.get('data_chiusura')),
        'valore_pratica': _txt(pratica_data.get('valore_pratica')),
        'tipo_pratica': _txt(pratica_data.get('tipo_pratica')),
        'settore_pratica': _txt(pratica_data.get('settore_pratica')),
        'materia_pratica': _txt(pratica_data.get('materia_pratica')),
        'tipo_tariffe': tipo_tariffe,
        'avvocato_referente': _txt(avv_ref),
        'avvocato_in_mandato': [ _txt(x) for x in (avv_mand or []) if _txt(x) ],
        'preventivo_inviato': bool(pratica_data.get('preventivo') or pratica_data.get('preventivo_inviato')),
        'note': _txt(pratica_data.get('note')),
        'tariffe_contenzioso': pratica_data.get('tariffe_contenzioso') or {},
        'tariffe_stragiudiziale': pratica_data.get('tariffe_stragiudiziale') or {},
        'preventivi': pratica_data.get('preventivi') or {},
        'preventivi_stragiudiziale': pratica_data.get('preventivi_stragiudiziale') or {},
        'scadenze': pratica_data.get('scadenze') or [],
        'totale_contenzioso': _somma_tariffe_sezione(pratica_data, 'contenzioso') + _somma_tabelle_sezione(pratica_data, 'contenzioso'),
        'totale_stragiudiziale': _somma_tariffe_sezione(pratica_data, 'stragiudiziale') + _somma_tabelle_sezione(pratica_data, 'stragiudiziale'),
        'totale_generale': 0.0,
        'updated_at': datetime.now().isoformat(timespec='seconds'),
        'anagrafica': {
            'tipo_cliente': 'Impresa' if (anagrafica_data.get('giuridiche')) else 'Persona',
            'persone_giuridiche': anagrafica_data.get('giuridiche') or [],
            'persone_fisiche': anagrafica_data.get('fisiche') or [],
        }
    }
    record['totale_generale'] = float(record['totale_contenzioso']) + float(record['totale_stragiudiziale'])
    return record

# ----------------- API principale -----------------

def salva_pratica(pratica_data: Dict[str, Any], anagrafica_data: Dict[str, Any], filename: Optional[str] = None) -> Optional[str]:
    """Salva la pratica in JSON secondo due modalità:
       - Scrive/aggiorna il canonico pratica.json dentro la cartella della pratica.
       - Crea SEMPRE:
           (a) copia timestampata nella cartella della pratica: <num>_<anno>_gp_<DDMMYYYY>_<HHMMSS>.json
           (b) backup dell'app sovrascrivibile: archivio/backups_json/<num>_<anno>_gp.json
    """
    pratica_path = _txt(pratica_data.get('percorso_pratica'))
    if not pratica_path:
        ui.notify('Percorso pratica non impostato: apri la pratica dal popup e riprova', type='warning')
        return None

    try:
        os.makedirs(pratica_path, exist_ok=True)
    except Exception as e:
        ui.notify(f'Errore accesso cartella pratica: {e}', type='negative')
        return None

    record = _build_record(pratica_data, anagrafica_data)

    canon_path = Path(pratica_path) / 'pratica.json'

    with _lock(canon_path):
        before = _read_existing(canon_path)
        pretty = json.dumps(record, ensure_ascii=False, indent=2)
        _atomic_write_text(canon_path, pretty)
        append_history(Path(pratica_path), actor='user', action='save_pratica', before=before, after=record)

    try:
        base_id = _safe_filename_from_id(pratica_data.get('id_pratica', ''))
        out_ds = dual_save(
            pratica_folder=Path(pratica_path),
            backup_dir=Path('archivio/backups_json'),
            base_id=base_id,
            json_text=pretty
        )
        ui.notify(f"Salvato: {Path(out_ds['timestamped_path']).name}", type='positive')
        ui.notify(f"Backup aggiornato: {Path(out_ds['backup_path']).name}", type='positive')
    except Exception as e:
        ui.notify(f'Dual-save non riuscito: {e}', type='warning')

    try:
        reindex(root=Path('archivio'), db_path=Path('archivio/indice.sqlite'))
    except Exception as e:
        ui.notify(f'Reindex fallito: {e}', type='warning')

    _append_logs(pratica_path, f"SALVATAGGIO_JSON canonico={canon_path}")
    return str(canon_path)

