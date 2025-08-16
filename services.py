from __future__ import annotations
from typing import Any, Dict, Tuple
from dataclasses import is_dataclass, asdict

# Import opzionale per compatibilità con i vecchi modelli:
try:
    from models import Pratica, PersonaFisica, PersonaGiuridica, RigaTariffa  # type: ignore
except Exception:  # se i modelli non esistono più, continuiamo in modalità dict-pura
    Pratica = PersonaFisica = PersonaGiuridica = RigaTariffa = object  # type: ignore


# ----------------- helpers -----------------

def _as_dict(obj: Any) -> Dict[str, Any]:
    """Converte pydantic/dataclass/oggetti 'semplici' in dict; se è già dict lo ritorna."""
    if isinstance(obj, dict):
        return obj
    # pydantic v2
    for attr in ("model_dump", "dict"):
        if hasattr(obj, attr) and callable(getattr(obj, attr)):
            try:
                if attr == "model_dump":
                    return getattr(obj, attr)(mode="python")
                return getattr(obj, attr)()
            except Exception:
                pass
    # dataclass
    if is_dataclass(obj):
        try:
            return asdict(obj)
        except Exception:
            pass
    # fallback grezzo
    try:
        return dict(obj.__dict__)
    except Exception:
        return {"value": str(obj)}

def _is_model_pratica(p: Any) -> bool:
    """True se è un oggetto con attributi stile modelli (contenzioso.tariffe, ecc.)."""
    return hasattr(p, "contenzioso") and hasattr(p, "stragiudiziale")

def _ensure_list(container: Dict[str, Any], key: str) -> None:
    if key not in container or not isinstance(container.get(key), list):
        container[key] = []

def _append_tariffa_json(pratica_data: Dict[str, Any], sezione: str, riga: Dict[str, Any]) -> None:
    """
    Aggiunge una riga in pratica_data['tariffe_<sezione>'][tipo].
    'tipo' è dedotto da chiavi comuni ('tipo', 'Tipo'); default 'Generica'.
    """
    blocco_key = f"tariffe_{sezione}"
    blocco = pratica_data.setdefault(blocco_key, {})
    if not isinstance(blocco, dict):
        pratica_data[blocco_key] = blocco = {}

    tipo = (riga.get("tipo") or riga.get("Tipo") or "Generica")
    righe = blocco.setdefault(str(tipo), [])
    if not isinstance(righe, list):
        blocco[str(tipo)] = righe = []
    righe.append(riga)


# ----------------- API retro-compatibili -----------------

def aggiungi_persona_fisica(pratica: Any, pf: Any) -> None:
    """Accetta pratica modello o dict. Appende pf a 'anagrafica_persone'."""
    if _is_model_pratica(pratica):
        # vecchio modello
        try:
            pratica.anagrafica_persone.append(pf)  # type: ignore[attr-defined]
            return
        except Exception:
            pass
    # JSON/dict
    pdata = pratica if isinstance(pratica, dict) else _as_dict(pratica)
    _ensure_list(pdata, "anagrafica_persone")
    pdata["anagrafica_persone"].append(_as_dict(pf))

def aggiungi_persona_giuridica(pratica: Any, pg: Any) -> None:
    """Accetta pratica modello o dict. Appende pg a 'anagrafica_imprese'."""
    if _is_model_pratica(pratica):
        try:
            pratica.anagrafica_imprese.append(pg)  # type: ignore[attr-defined]
            return
        except Exception:
            pass
    pdata = pratica if isinstance(pratica, dict) else _as_dict(pratica)
    _ensure_list(pdata, "anagrafica_imprese")
    pdata["anagrafica_imprese"].append(_as_dict(pg))

def aggiungi_tariffa_contenzioso(pratica: Any, riga: Any) -> None:
    """
    Se 'pratica' è un modello, usa .contenzioso.tariffe.append(riga).
    Altrimenti scrive in pratica_data['tariffe_contenzioso'][tipo].
    """
    if _is_model_pratica(pratica):
        try:
            pratica.contenzioso.tariffe.append(riga)  # type: ignore[attr-defined]
            return
        except Exception:
            pass
    pdata = pratica if isinstance(pratica, dict) else _as_dict(pratica)
    _append_tariffa_json(pdata, "contenzioso", _as_dict(riga))

def aggiungi_tariffa_stragiudiziale(pratica: Any, riga: Any) -> None:
    """
    Se 'pratica' è un modello, usa .stragiudiziale.tariffe.append(riga).
    Altrimenti scrive in pratica_data['tariffe_stragiudiziale'][tipo].
    """
    if _is_model_pratica(pratica):
        try:
            pratica.stragiudiziale.tariffe.append(riga)  # type: ignore[attr-defined]
            return
        except Exception:
            pass
    pdata = pratica if isinstance(pratica, dict) else _as_dict(pratica)
    _append_tariffa_json(pdata, "stragiudiziale", _as_dict(riga))

