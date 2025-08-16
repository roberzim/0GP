
from __future__ import annotations
from pathlib import Path
from typing import Optional, Dict, Any
from models import Pratica
from repo import load_pratica, save_pratica
from dual_save import dual_save

import re

def crea_pratica_nuova(cartella: Path, id_pratica: str, dati_base: Optional[Dict[str, Any]] = None, actor: str = "user") -> Path:
    """Crea una nuova pratica (vuota + dati_base opzionali) e salva JSON nella cartella indicata"""
    p = Pratica(id_pratica=id_pratica, **(dati_base or {}))
    return save_pratica(p, cartella, actor=actor)

def carica_pratica(cartella: Path) -> Pratica:
    return load_pratica(cartella)

def salva_pratica_con_backup(pratica: Pratica, cartella: Path, app_backup_dir: Path | str = "./archivio/backups_json", actor: str = "user") -> Dict[str, str]:
    """Salva pratica.json nella cartella indicata e salva anche il backup sovrascrivibile dell'app."""
    # Salva stato "canonico" (pratica.json + history.jsonl)
    save_pratica(pratica, cartella, actor=actor)
    # Salva copia timestamp + backup nell'app
    # compat: sostituisce save_pratica_json → save_pratica + dual_save
p = save_pratica(pratica, cartella, actor=actor if 'actor' in locals() else 'user')
base_id = _sanitize_base_id(str(pratica.id_pratica)) or f"pratica_{datetime.now():%Y%m%d_%H%M%S}"
out = dual_save(pratica_folder=cartella, backup_dir=app_backup_dir, base_id=base_id)
return out

def _sanitize_base_id(s: str) -> str:
    s = (s or "").replace("/", "")
    return re.sub(r"[^A-Za-z0-9_-]+", "", s)
