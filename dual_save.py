#!/usr/bin/env python3
from __future__ import annotations
from typing import Dict, Any, Optional
from pathlib import Path
import json, traceback

from salva_tutto import salva_tutto

def _unwrap_pratica(p: Any) -> Optional[Dict[str, Any]]:
    if p is None:
        return None
    if isinstance(p, dict):
        if any(k in p for k in ("id_pratica", "id", "codice")):
            return p
        for k in ("pratica", "data", "record"):
            v = p.get(k)
            if isinstance(v, dict) and any(kk in v for kk in ("id_pratica", "id", "codice")):
                return v
        return p
    return None

def _load_pratica_from_folder(folder: str) -> Optional[Dict[str, Any]]:
    if not folder:
        return None
    p = Path(folder)
    if not p.exists():
        return None
    # snapshot timestampati
    candidates = sorted(p.glob("*_gp_*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
    for f in candidates:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                if not any(k in data for k in ("id_pratica", "id", "codice")):
                    stem = f.stem
                    if "_gp_" in stem:
                        maybe_id = stem.split("_gp_")[0]
                        if maybe_id:
                            data.setdefault("id_pratica", maybe_id)
                return data
        except Exception:
            continue
    # fallback: pratica.json
    pj = p / "pratica.json"
    if pj.exists():
        try:
            data = json.loads(pj.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return None

def dual_save(
    *args,
    pratica: Optional[Dict[str, Any]] = None,
    pratica_folder: Optional[str] = None,
    json_root: str = "app_pratiche",
    db_path: Optional[str] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    Wrapper retro-compat:
      - Accetta: dual_save(pratica), dual_save(pratica=...), dual_save(pratica_folder=...)
      - Se manca 'pratica' ma esiste 'pratica_folder', prova a ricostruire dai JSON nella cartella
      - Ritorna un dict ricco (quello di salva_tutto) con:
          * 'timestamped_path' e 'timestamped_sql_path'
          * 'paths' dettagliati
          * 'pratica' originale
    """
    try:
        p = _unwrap_pratica(pratica)
        if p is None and args:
            p = _unwrap_pratica(args[0])
        if p is None and pratica_folder:
            p = _load_pratica_from_folder(pratica_folder)
        if not isinstance(p, dict):
            raise RuntimeError(
                "dual_save: 'pratica' mancante o non valida. "
                "Passa un dict con id_pratica/id/codice oppure fornisci pratica_folder con un JSON salvato."
            )
        if pratica_folder:
            p.setdefault("percorso_pratica", pratica_folder)

        # delega a salva_tutto: ritorna un dict con timestamped_path
        result = salva_tutto(p, json_root=json_root, db_path=db_path)
        return result
    except Exception:
        traceback.print_exc()
        raise
