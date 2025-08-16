from __future__ import annotations
import json, time, os, hashlib
from pathlib import Path
from contextlib import contextmanager
from typing import Optional, Dict, Any, Union
from datetime import datetime
from models import Pratica
from history import append_history

# ---------------- utils ----------------

def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")

def _canonical_json(obj: Any) -> str:
    """JSON stabile per confronti/diff (mantiene liste, ordina solo le chiavi dict)."""
    if obj is None:
        return "null"
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

def _atomic_write_text(path: Path, text: str) -> None:
    """Scrittura atomica robusta su stesso filesystem (tmp + fsync + replace)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
        try:
            f.flush()
            os.fsync(f.fileno())
        except Exception:
            # su alcuni FS non è necessario/permesso
            pass
    os.replace(tmp, path)

@contextmanager
def _lock(path: Path, timeout: float = 10.0, stale: float = 30.0):
    """Lock file semplice con TTL: evita corruzione su scritture concorrenti."""
    lock = path.with_suffix(path.suffix + ".lock")
    start = time.monotonic()
    while lock.exists():
        try:
            # se il lock è vecchio, assumilo stantìo e rimuovilo
            if time.time() - lock.stat().st_mtime > stale:
                lock.unlink(missing_ok=True)
                break
        except Exception:
            pass
        if time.monotonic() - start > timeout:
            raise TimeoutError(f"Timeout acquisizione lock su {path}")
        time.sleep(0.1)
    try:
        # contenuto informativo nel lock (pid + timestamp)
        try:
            lock.write_text(f"{os.getpid()} @ {time.time()}", encoding="utf-8")
        except Exception:
            pass
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
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None

def _save_dict(folder: Path, after: Dict[str, Any], actor: str = "system") -> Path:
    """Routine condivisa: salva dict in pratica.json con lock, atomico e history."""
    folder.mkdir(parents=True, exist_ok=True)
    p = folder / "pratica.json"

    with _lock(p):
        before = _read_existing(p)

        # default updated_at se assente
        after = dict(after) if after is not None else {}
        after.setdefault("updated_at", _now_iso())

        # confronta contenuti canonici per evitare riscritture inutili
        before_canon = _canonical_json(before) if before is not None else None
        after_canon = _canonical_json(after)
        if before_canon == after_canon:
            # nessun cambiamento: esci silenziosamente
            return p

        # scrittura atomica
        pretty = json.dumps(after, ensure_ascii=False, indent=2)
        _atomic_write_text(p, pretty)

        # history
        append_history(folder, actor=actor, action="save_pratica", before=before, after=after)

    return p

# ---------------- API ----------------

def load_pratica(folder: Path) -> Pratica:
    p = folder / "pratica.json"
    if not p.exists():
        raise FileNotFoundError(f"Manca {p}")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        raise ValueError(f"JSON non valido in {p}: {e}") from e
    return Pratica(**data)

def save_pratica(pratica: Pratica, folder: Path, actor: str = "system") -> Path:
    """Scrive pratica.json + history.jsonl in modo sicuro/atomico.
       Se i contenuti non cambiano, non riscrive e non aggiunge history.
    """
    # aggiorna updated_at anche sull'istanza, se presente
    try:
        if hasattr(pratica, "updated_at"):
            setattr(pratica, "updated_at", datetime.now())
    except Exception:
        pass

    try:
        after: Dict[str, Any] = pratica.model_dump(mode="json")  # Pydantic v2
    except Exception as e:
        # fallback: tentativo generico (Pydantic v1 o dataclass-like)
        try:
            after = json.loads(json.dumps(pratica, default=lambda o: getattr(o, "dict", lambda: str(o))()))
        except Exception as e2:
            raise ValueError(f"Impossibile serializzare la pratica: {e2}") from e2

    return _save_dict(Path(folder), after, actor=actor)

def write_pratica(folder: Path, data: Union[Dict[str, Any], Pratica], actor: str = "system") -> Path:
    """Variante che accetta direttamente un dict (o un'istanza Pratica).
       Converte e delega alla routine condivisa, con lock/atomico/history.
    """
    if isinstance(data, Pratica):
        return save_pratica(data, folder, actor=actor)
    if not isinstance(data, dict):
        raise TypeError("write_pratica: 'data' deve essere dict o Pratica")
    # garantisci updated_at
    data = dict(data)
    data.setdefault("updated_at", _now_iso())
    return _save_dict(Path(folder), data, actor=actor)
