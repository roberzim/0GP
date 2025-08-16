#!/usr/bin/env python3
from __future__ import annotations
import os, json, tempfile, shutil
from pathlib import Path
from typing import Dict, Any, Optional
import repo_sqlite
from db_core import get_connection

def _atomic_write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name, dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)  # atomic rename
    finally:
        try:
            os.remove(tmp)
        except FileNotFoundError:
            pass

def salva_tutto(pratica: Dict[str, Any], *, json_root: str = "app_pratiche", db_path: Optional[str] = None) -> None:
    """Dual-write: JSON snapshot + SQLite upsert. JSON prima, DB poi. In caso di errore DB il JSON rimane."""
    pid = pratica.get("id_pratica") or pratica.get("id") or pratica.get("codice")
    if not pid:
        raise ValueError("salva_tutto: pratica senza id_pratica")
    # 1) JSON
    folder = Path(json_root) / pid
    _atomic_write_json(folder / "pratica.json", pratica)
    # 2) DB
    if db_path is None:
        db_path = os.environ.get("GP_DB_PATH", os.path.join("archivio","0gp.sqlite"))
    try:
        with get_connection(db_path) as con:
            repo_sqlite.upsert_pratica(con, pratica)
    except Exception as e:
        # Log minimal fallback; in un'app reale usare logging
        print(f"[WARN] DB write failed, JSON salvato comunque: {e}")
        # non rilanciamo: preferiamo non bloccare il salvataggio lato UI

# retro-compat con server.py
def salva_pratica(pratica, json_root="app_pratiche", db_path=None):
    return salva_tutto(pratica, json_root=json_root, db_path=db_path)
