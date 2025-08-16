from __future__ import annotations
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, Union
import json
import re
import os

try:
    from pydantic import BaseModel
    _HAS_PYDANTIC = True
except Exception:
    BaseModel = object  # type: ignore
    _HAS_PYDANTIC = False


def _normalize_id(id_pratica: str) -> str:
    """Trasforma '1/2025' -> '1_2025' e rimuove caratteri non sicuri per i nomi file."""
    s = (id_pratica or '').strip().replace('/', '_').replace('\\', '_')
    s = re.sub(r'[^0-9A-Za-z._-]+', '_', s)
    return s or 'SENZA_ID'


def build_filenames(id_pratica: str, when: datetime | None = None) -> tuple[str, str]:
    """
    Ritorna (timestamped_filename, backup_filename) senza path:
      - '1_2025_gp_11082025_170314.json'
      - '1_2025_gp.json'
    """
    when = when or datetime.now()
    ts = when.strftime('%d%m%Y_%H%M%S')
    base = _normalize_id(id_pratica)
    backup_name = f'{base}_gp.json'
    ts_name = f'{base}_gp_{ts}.json'
    return ts_name, backup_name


def _to_dict(pratica: Union[Dict[str, Any], "BaseModel"]) -> Dict[str, Any]:
    if _HAS_PYDANTIC and isinstance(pratica, BaseModel):  # type: ignore
        try:
            return pratica.model_dump(mode="json")  # Pydantic v2 (serializza datetime -> ISO)
        except Exception:
            try:
                return pratica.dict()  # Pydantic v1
            except Exception:
                pass
    if isinstance(pratica, dict):
        return pratica
    raise TypeError("Unsupported pratica type; pass a dict or a Pydantic model")


def _atomic_write_text(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def save_pratica_json(
    pratica: Union[Dict[str, Any], "BaseModel"],
    target_dir: Path | str,
    id_pratica: str,
    app_backup_dir: Path | str = "./archivio/backups_json",
) -> dict:
    """
    Salva:
      1) JSON nella cartella utente con nome 'ID_gp_DDMMYYYY_HHMMSS.json'
      2) JSON di backup nella cartella app con nome 'ID_gp.json' (sovrascrivibile)

    Ritorna un dict con percorsi e dimensione in byte:
      { "timestamped_path": "...", "backup_path": "...", "bytes": 1234 }
    """
    target_dir = Path(target_dir)
    backup_dir = Path(app_backup_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    backup_dir.mkdir(parents=True, exist_ok=True)

    # normalizza e genera nomi file
    ts_name, backup_name = build_filenames(id_pratica)

    # dati serializzabili
    data = _to_dict(pratica)
    # aggiorna/aggiungi updated_at se mancante
    data.setdefault("updated_at", datetime.now().isoformat(timespec="seconds"))

    # percorsi finali
    ts_path = target_dir / ts_name
    backup_path = backup_dir / backup_name

    # JSON pretty
    js = json.dumps(data, ensure_ascii=False, indent=2)

    # scritture atomiche
    _atomic_write_text(ts_path, js)
    _atomic_write_text(backup_path, js)

    return {
        "timestamped_path": str(ts_path),
        "backup_path": str(backup_path),
        "bytes": len(js.encode("utf-8")),
    }

