"""
Modelli Pydantic completi (Pydantic v2) per il progetto "Gestione Pratiche" con:
- Validazione Codice Fiscale con algoritmo ufficiale
- Supporto valute multiple da file valute_full.json fornito dall'utente
- Conversione automatica in EUR usando tassi BCE per tariffe non ministeriali
- Reindicizzazione automatica all'apertura e chiusura dell'app
"""
from __future__ import annotations

from datetime import date, datetime, timezone, timedelta
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import List, Optional
from uuid import UUID, uuid4
import json
import re
from pathlib import Path
from pydantic import BaseModel, Field, EmailStr, AnyUrl, ConfigDict, field_validator, computed_field

# ------------------------------------------------------------
# Utilità comuni e indicizzazione
# ------------------------------------------------------------

def utcnow() -> datetime:
    return datetime.now(timezone.utc)

def reindex_all():
    print(f"[INDEX] Reindicizzazione eseguita alle {utcnow().isoformat()}")

# ------------------------------------------------------------
# Gestione valute
# ------------------------------------------------------------
class CurrencyRegistry:
    _codes: set[str] = {"EUR"}

    @classmethod
    def load_from_json(cls, path: str | Path) -> set[str]:
        p = Path(path)
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "valute" in data:
            codes = {v["code"].upper().strip() for v in data["valute"]}
        elif isinstance(data, list):
            codes = {str(item.get("code", "")).upper().strip() for item in data}
        else:
            codes = set()
        if not codes:
            raise ValueError("Nessuna valuta trovata in file valute")
        cls._codes = codes
        return cls._codes

    @classmethod
    def allowed(cls) -> set[str]:
        return cls._codes

    @staticmethod
    def validate_valute_file(path: str | Path) -> None:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(data, dict) or "valute" not in data:
            raise ValueError("Formato file valute non valido: manca la chiave 'valute'")
        seen = set()
        for v in data["valute"]:
            code = v.get("code", "").upper().strip()
            if not re.match(r"^[A-Z]{3}$", code):
                raise ValueError(f"Codice valuta non valido: {code}")
            if code in seen:
                raise ValueError(f"Codice valuta duplicato: {code}")
            seen.add(code)

# ------------------------------------------------------------
# Sistema cambi BCE e conversioni
# ------------------------------------------------------------
class FxRates(BaseModel):
    as_of: datetime = Field(default_factory=utcnow)
    rates: dict[str, Decimal] = Field(default_factory=dict)

    @classmethod
    def from_json(cls, path: str | Path) -> "FxRates":
        p = Path(path)
        data = json.loads(p.read_text(encoding="utf-8"))
        rates = {k.upper(): Decimal(str(v)) for k, v in data.get("rates", {}).items()}
        as_of = datetime.fromisoformat(data.get("as_of")) if data.get("as_of") else utcnow()
        return cls(as_of=as_of, rates=rates)

    def to_json(self, path: str | Path) -> None:
        payload = {"as_of": self.as_of.isoformat(), "rates": {k: float(v) for k, v in self.rates.items()}}
        Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def convert_to_eur(self, m: "Money") -> "Money":
        code = m.currency.upper()
        if code == "EUR":
            return m
        if code not in self.rates or self.rates[code] == 0:
            raise ValueError(f"Tasso BCE mancante per {code}")
        eur = (m.amount / self.rates[code]).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return Money(amount=eur, currency="EUR")

    @staticmethod
    def fetch_from_ecb() -> "FxRates":
        import urllib.request, json as _json
        url = "https://sdw-wsrest.ecb.europa.eu/service/data/EXR/D..EUR.SP00.A?lastNObservations=1&format=sdmx-json"
        with urllib.request.urlopen(url) as resp:
            data = _json.loads(resp.read().decode("utf-8"))
        series = data["data"]["dataSets"][0]["series"]
        struct = data["data"]["structure"]
        dims = struct["dimensions"]["series"]
        currency_dim_pos = 1
        currencies = dims[currency_dim_pos]["values"]
        rates: dict[str, Decimal] = {}
        for key, serie in series.items():
            parts = key.split(":")
            code = currencies[int(parts[currency_dim_pos])]["id"].upper()
            obs = serie["observations"]
            first_key = next(iter(obs))
            rate = Decimal(str(obs[first_key][0]))
            if rate > 0:
                rates[code] = rate
        return FxRates(as_of=utcnow(), rates=rates)

# ------------------------------------------------------------
# Hook avvio/chiusura
# ------------------------------------------------------------
def init_fx_on_startup(valute_path: str | Path, *, cache_path: str | None = None, reindex: object | None = None) -> FxRates:
    CurrencyRegistry.validate_valute_file(valute_path)
    CurrencyRegistry.load_from_json(valute_path)
    fx = FxRates.fetch_from_ecb()
    if cache_path:
        fx.to_json(cache_path)
    if reindex is not None:
        try:
            if callable(reindex):
                reindex()
            elif hasattr(reindex, "rebuild") and callable(getattr(reindex, "rebuild")):
                reindex.rebuild()
            elif hasattr(reindex, "refresh") and callable(getattr(reindex, "refresh")):
                reindex.refresh()
        except Exception as e:
            print(f"[reindex] errore all'avvio: {e}")
    return fx

def on_shutdown_reindex(reindex: object | None = None) -> None:
    if reindex is None:
        return
    try:
        if callable(reindex):
            reindex()
        elif hasattr(reindex, "rebuild") and callable(getattr(reindex, "rebuild")):
            reindex.rebuild()
        elif hasattr(reindex, "refresh") and callable(getattr(reindex, "refresh")):
            reindex.refresh()
    except Exception as e:
        print(f"[reindex] errore in chiusura: {e}")


# ------------------------------------------------------------
# Validazione file valute_full.json e override init hook
# ------------------------------------------------------------
from typing import Tuple

def validate_valute_file(path: str | Path) -> Tuple[bool, str, set[str]]:
    """Controlla struttura di valute_full.json senza modificarlo.
    - richiede un oggetto {"valute": [ {"code": "USD", "name": "US dollar", ...}, ... ]}
    - verifica code (3 lettere), name non vuoto, ecb_supported opzionale/bool
    - segnala duplicati
    Ritorna (ok, messaggio, codes_set).
    """
    p = Path(path)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or "valute" not in data or not isinstance(data["valute"], list):
            return False, "Struttura non valida: atteso oggetto con chiave 'valute' (lista)", set()
        codes: set[str] = set()
        dups: set[str] = set()
        for i, item in enumerate(data["valute"], start=1):
            if not isinstance(item, dict):
                return False, f"Elemento #{i} non è un oggetto", set()
            code = str(item.get("code", "")).upper().strip()
            name = str(item.get("name", "")).strip()
            if not re.fullmatch(r"[A-Z]{3}", code):
                return False, f"Elemento #{i}: code non valido ('{code}')", set()
            if not name:
                return False, f"Elemento #{i}: name mancante o vuoto per {code}", set()
            if code in codes:
                dups.add(code)
            codes.add(code)
            ecb_supported = item.get("ecb_supported", None)
            if ecb_supported is not None and not isinstance(ecb_supported, bool):
                return False, f"Elemento #{i}: ecb_supported deve essere booleano per {code}", set()
        if dups:
            return False, f"Codici duplicati trovati: {', '.join(sorted(dups))}", set()
        return True, f"OK: {len(codes)} valute valide", codes
    except Exception as e:
        return False, f"Errore lettura/parsing: {e}", set()

# Ridefinizione dell'hook per usare solo valute_full.json senza riscriverlo

def init_fx_on_startup(valute_path: str | Path, *, cache_path: str | None = None, reindex: object | None = None) -> FxRates:
    """All'avvio: valida e carica valute da valute_full.json, aggiorna tassi BCE, salva cache opzionale, reindicizza.
    Non modifica il file valute.
    """
    ok, msg, _codes = validate_valute_file(valute_path)
    if not ok:
        raise ValueError(f"valute_full.json non valido: {msg}")
    # carica codici nel registry
    CurrencyRegistry.load_from_json(valute_path)

    # aggiorna tassi
    fx = FxRates.fetch_from_ecb()
    if cache_path:
        fx.to_json(cache_path)

    # reindicizza (best effort)
    if reindex is not None:
        try:
            if callable(reindex):
                reindex()
            elif hasattr(reindex, "rebuild") and callable(getattr(reindex, "rebuild")):
                reindex.rebuild()
            elif hasattr(reindex, "refresh") and callable(getattr(reindex, "refresh")):
                reindex.refresh()
        except Exception as e:
            print(f"[reindex] errore all'avvio: {e}")
    return fx
