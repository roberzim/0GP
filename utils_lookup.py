# utils_lookup.py
from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, List, Optional
from functools import lru_cache
import os, json

# Root dei file JSON (override con variabile d'ambiente GP_LIB_JSON)
LIB = Path(os.getenv("GP_LIB_JSON", "lib_json"))

# ------------------ helpers interni ------------------

def _read_text(path: Path) -> str:
    """Legge testo UTF-8 rimuovendo un eventuale BOM."""
    s = path.read_text(encoding="utf-8")
    return s.lstrip("\ufeff")

def _to_int(x: Any) -> Optional[int]:
    try:
        s = str(x).strip()
        if s == "":
            return None
        return int(s)
    except Exception:
        return None

@lru_cache(maxsize=64)
def _read_json(name: str) -> Dict[str, Any]:
    """Legge lib_json/<name>.json e ritorna un dict ({} se non esiste o non valido)."""
    p = LIB / f"{name}.json"
    if not p.exists():
        return {}
    try:
        return json.loads(_read_text(p)) or {}
    except Exception:
        return {}

def clear_caches() -> None:
    """Chiama questa dopo aver scritto/aggiornato JSON in lib_json."""
    _read_json.cache_clear()  # type: ignore[attr-defined]

def _get_list_field(obj: Dict[str, Any], key: str) -> List[Any]:
    """Ritorna obj[key] se è una lista, altrimenti []."""
    val = obj.get(key)
    return val if isinstance(val, list) else []

def _load(name: str, key: str) -> List[Any]:
    """Carica una lista da lib_json/<name>.json prendendo la chiave <key>."""
    data = _read_json(name)
    return _get_list_field(data, key)

# ------------------ normalizzazioni utili ------------------

def _normalize_id_record(rec: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalizza un record del registro pratiche a un set di chiavi coerente.
    Supporta:
      - nuovo schema: {"version": 1, "records": [...]}
      - vecchio schema: {"id_pratiche": [...]}
    """
    num  = _to_int(rec.get("num_pratica"))
    anno = _to_int(rec.get("anno_pratica"))
    idp  = rec.get("id_pratica")
    if not idp and (num is not None) and (anno is not None):
        idp = f"{num}/{anno}"

    # percorso: preferisci 'percorso_pratica'; fallback a link_* se presenti
    percorso = (
        rec.get("percorso_pratica")
        or rec.get("link_percorso_pratica")
        or rec.get("link_cartella")
        or ""
    )

    return {
        "id_pratica": idp or "",
        "num_pratica": num,
        "anno_pratica": anno,
        "nome_pratica": rec.get("nome_pratica") or "",
        "percorso_pratica": percorso,
        "created_at": rec.get("created_at") or "",
        "created_by": rec.get("created_by") or "",
    }

# ------------------ API di caricamento ------------------

def load_avvocati() -> List[str]:
    return _load("avvocati", "avvocati")

def load_materie() -> List[str]:
    return _load("materie", "materie")

def load_settori() -> List[str]:
    return _load("settori", "settori")

def load_tariffe() -> List[str]:
    return _load("tariffe", "tariffe")

def load_tipo_pratica() -> List[str]:
    return _load("tipo_pratica", "tipo_pratica")

def load_posizioni() -> List[str]:
    return _load("posizioni", "posizioni")

def load_persone_fisiche() -> List[Dict[str, Any]]:
    return _load("persone_fisiche", "persone_fisiche")

def load_persone_giuridiche() -> List[Dict[str, Any]]:
    return _load("persone_giuridiche", "persone_giuridiche")

def load_id_pratiche() -> List[Dict[str, Any]]:
    """
    Carica il registro pratiche in forma di lista normalizzata.
    - Se il file usa il nuovo schema: {"version": 1, "records": [...]}
    - Se il file usa il vecchio schema: {"id_pratiche": [...]}
    Ritorna sempre una lista di dict con chiavi standardizzate, ordinate per (anno,num).
    """
    data = _read_json("id_pratiche")

    if "records" in data:
        raw = _get_list_field(data, "records")
    elif "id_pratiche" in data:
        raw = _get_list_field(data, "id_pratiche")
    else:
        raw = []

    norm = [_normalize_id_record(r if isinstance(r, dict) else {}) for r in raw]
    # Ordina per anno e numero (i None finiscono in fondo)
    norm.sort(key=lambda r: (r["anno_pratica"] is None, r["anno_pratica"], r["num_pratica"] is None, r["num_pratica"]))
    return norm

