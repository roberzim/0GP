from __future__ import annotations
"""
dual_save.py — salva due copie del JSON della pratica.

1) Copia TIMESTAMPATA nella CARTELLA della pratica:
   <num>_<anno>_gp_<DDMMYYYY>_<HHMMSS>.json

2) Copia BACKUP “di app” sovrascrivibile in backup_dir:
   <num>_<anno>_gp.json

Uso:
    out = dual_save(
        pratica_folder=Path('/percorso/cliente/pratica'),
        backup_dir=Path('archivio/backups_json'),
        base_id='9_2025',
        data=pratica_dict,   # oppure json_text='...'
    )
"""

from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any
import os
import json
import re  # FIX: serviva per _sanitize_base_id

def _atomic_write_text(path: Path, text: str) -> None:
    """Scrittura atomica: tmp + replace (stesso filesystem)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(str(path) + '.tmp')
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write(text)
        try:
            f.flush(); os.fsync(f.fileno())
        except Exception:
            pass
    os.replace(tmp, path)

def _sanitize_base_id(s: str) -> str:
    """Conserva solo [A-Za-z0-9_-]; rimuove separatori come '/'."""
    s = s or ''
    s = s.replace('/', '')
    return re.sub(r'[^A-Za-z0-9_-]+', '', s)

def dual_save(
    pratica_folder: Path | str,
    backup_dir: Path | str,
    base_id: str,
    *,
    data: Optional[Dict[str, Any]] = None,
    json_text: Optional[str] = None,
    timestamp: Optional[datetime] = None,
) -> Dict[str, str]:
    """Crea due copie del JSON pratica:
    1) Timestamp nella cartella pratica: <ID>_gp_DDMMYYYY_HHMMSS.json
    2) Backup app sovrascrivibile:       <ID>_gp.json in backup_dir

    Sorgente:
      - se 'data' è passato, serializza 'data'
      - altrimenti se 'json_text' è passato, usa quello
      - altrimenti legge <pratica_folder>/pratica.json

    Ritorna dict con percorsi e dimensione in byte.
    """
    pratica_folder = Path(pratica_folder)
    backup_dir = Path(backup_dir)
    base_id = _sanitize_base_id(str(base_id))
    if not base_id:
        raise ValueError("dual_save: 'base_id' non può essere vuoto")

    # determina la sorgente JSON
    if data is not None:
        js = json.dumps(data, ensure_ascii=False, indent=2)
        source = 'data'
    elif json_text is not None:
        js = str(json_text)
        source = 'json_text'
    else:
        canon = pratica_folder / 'pratica.json'
        if not canon.exists():
            raise FileNotFoundError(
                f'dual_save: sorgente {canon} non trovata; passa \'data\' o \'json_text\''
            )
        js = canon.read_text(encoding='utf-8')
        source = 'pratica.json'

    # prepara i path di uscita
    ts = (timestamp or datetime.now()).strftime('%d%m%Y_%H%M%S')
    ts_name = f'{base_id}_gp_{ts}.json'
    ts_path = pratica_folder / ts_name
    backup_path = backup_dir / f'{base_id}_gp.json'

    # scritture atomiche
    _atomic_write_text(ts_path, js)
    _atomic_write_text(backup_path, js)

    return {
        'timestamped_path': str(ts_path),
        'backup_path': str(backup_path),
        'bytes': str(len(js.encode('utf-8'))),
        'source': source,
    }

