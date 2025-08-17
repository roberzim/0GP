"""Storage utilities centralizzati per 0GP (export SQL robusto)."""
from __future__ import annotations

import json, os, sqlite3, tempfile
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from datetime import datetime, date

try:
    from export_pratica_sql import export_pratica_sql  # opzionale
except Exception:
    export_pratica_sql = None  # type: ignore

def _register_sqlite_adapters_once() -> None:
    if getattr(_register_sqlite_adapters_once, "_done", False):
        return
    sqlite3.register_adapter(dict, lambda v: json.dumps(v, ensure_ascii=False, separators=(",", ":")))
    sqlite3.register_adapter(list, lambda v: json.dumps(v, ensure_ascii=False, separators=(",", ":")))
    sqlite3.register_adapter(bool, lambda v: 1 if v else 0)
    sqlite3.register_adapter(datetime, lambda v: v.isoformat())
    sqlite3.register_adapter(date, lambda v: v.isoformat())
    sqlite3.register_adapter(Decimal, lambda v: str(v))
    setattr(_register_sqlite_adapters_once, "_done", True)

def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name, dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            try:
                f.flush(); os.fsync(f.fileno())
            except Exception:
                pass
        os.replace(tmp, path)
    finally:
        try: os.remove(tmp)
        except Exception: pass

def _atomic_write_text(path: Path, text: str) -> None:
    _atomic_write_bytes(path, text.encode("utf-8"))

def _atomic_write_json(path: Path, data: Dict[str, Any]) -> None:
    _atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=2))

def _norm_id(raw_id: str) -> str:
    return "".join(ch if (ch.isalnum() or ch in "_-") else "_" for ch in str(raw_id))

def _timestamp_and_month() -> Tuple[str, str]:
    now = datetime.now()
    ts = now.strftime("%d%m%Y_%H%M%S")
    month_dir = f"{int(now.strftime('%m'))}_{now.strftime('%Y')}"
    return ts, month_dir

def _resolve_user_dir(pratica: Dict[str, Any]) -> Optional[Path]:
    for key in ("percorso_pratica", "user_dir", "cartella_pratica", "percorso"):
        v = pratica.get(key)
        if isinstance(v, str) and v.strip():
            return Path(v)
    return None

def _build_paths(pid_norm: str, ts: str, month_dir: str, json_root: str, user_dir: Optional[Path]) -> Dict[str, Path]:
    app_folder = Path(json_root) / pid_norm
    data_month_dir = Path("data") / month_dir
    app_json = app_folder / f"{pid_norm}_gp.json"
    app_sql  = app_folder / f"{pid_norm}_gp.sql"
    canon_json = app_folder / "pratica.json"
    user_json_ts = user_dir / f"{pid_norm}_gp_{ts}.json" if user_dir else None
    user_sql_ts  = user_dir / f"{pid_norm}_gp_{ts}.sql"  if user_dir else None
    data_json_ts = data_month_dir / f"{pid_norm}_gp_{ts}.json"
    data_sql_ts  = data_month_dir / f"{pid_norm}_gp_{ts}.sql"
    return {
        "app_folder": app_folder,
        "data_month_dir": data_month_dir,
        "app_json_path": app_json,
        "app_sql_path": app_sql,
        "canon_json_path": canon_json,
        "user_json_ts_path": user_json_ts,
        "user_sql_ts_path": user_sql_ts,
        "data_json_ts_path": data_json_ts,
        "data_sql_ts_path": data_sql_ts,
    }

def save_pratica(pratica: Dict[str, Any], *, json_root: str = "app_pratiche", db_path: Optional[str] = None) -> Dict[str, Any]:
    # id "raw" per DB/export; id normalizzato solo per nomi file
    pid_raw = pratica.get("id_pratica") or pratica.get("id") or pratica.get("codice")
    if not pid_raw:
        raise ValueError("save_pratica: pratica senza id_pratica / id / codice")
    pid_norm = _norm_id(str(pid_raw))

    ts, month_dir = _timestamp_and_month()
    user_dir = _resolve_user_dir(pratica)
    paths = _build_paths(pid_norm, ts, month_dir, json_root, user_dir)
    data_month_dir: Path = paths["data_month_dir"]

    # JSON
    _atomic_write_json(paths["app_json_path"], pratica)
    _atomic_write_json(paths["canon_json_path"], pratica)
    if paths["user_json_ts_path"] is not None:
        try: _atomic_write_json(paths["user_json_ts_path"], pratica)
        except Exception as e: print(f"[WARN] Impossibile scrivere JSON nella cartella utente '{user_dir}': {e}")
    try: _atomic_write_json(paths["data_json_ts_path"], pratica)
    except Exception as e: print(f"[WARN] Impossibile scrivere JSON in archivio app '{data_month_dir}': {e}")

    # DB
    if db_path is None:
        db_path = os.environ.get("GP_DB_PATH", os.path.join("archivio", "0gp.sqlite"))
    _register_sqlite_adapters_once()
    try:
        from repo_sqlite import upsert_pratica
        from db_core import get_connection
        with get_connection(db_path) as con:
            upsert_pratica(con, pratica)
    except Exception as e:
        print(f"[WARN] DB write failed, file JSON scritti comunque: {e}")

    # Export SQL: **USA pid_raw** (non normalizzato) per matchare il DB
    placeholder = f"-- Export vuoto per id_pratica={pid_raw} (nessuna riga trovata o errore).\n"
    if export_pratica_sql is not None:
        try:
            sql_dump = export_pratica_sql(db_path, str(pid_raw))
        except Exception as e:
            print(f"[WARN] Export SQL fallito per pratica {pid_raw}: {e}")
            sql_dump = None
    else:
        sql_dump = f"-- export_pratica_sql non disponibile per pratica {pid_raw}\n"

    if not isinstance(sql_dump, str) or not sql_dump.strip():
        sql_dump = placeholder

    _atomic_write_text(paths["app_sql_path"], sql_dump)
    if paths["user_sql_ts_path"] is not None:
        try: _atomic_write_text(paths["user_sql_ts_path"], sql_dump)
        except Exception as e: print(f"[WARN] Impossibile scrivere SQL nella cartella utente '{user_dir}': {e}")
    try: _atomic_write_text(paths["data_sql_ts_path"], sql_dump)
    except Exception as e: print(f"[WARN] Impossibile scrivere SQL in archivio app '{data_month_dir}': {e}")

    return {
        "ok": True,
        "id_pratica": pid_norm,
        "id_pratica_raw": str(pid_raw),
        "pratica": pratica,
        "db_path": db_path,
        "export_sql_available": export_pratica_sql is not None,
        "paths": {
            "app_json": str(paths["app_json_path"]),
            "app_sql": str(paths["app_sql_path"]),
            "app_canon_json": str(paths["canon_json_path"]),
            "user_json_ts": str(paths["user_json_ts_path"]) if paths["user_json_ts_path"] else None,
            "user_sql_ts": str(paths["user_sql_ts_path"]) if paths["user_sql_ts_path"] else None,
            "data_json_ts": str(paths["data_json_ts_path"]),
            "data_sql_ts": str(paths["data_sql_ts_path"]),
        },
        "timestamped_path": str(paths["user_json_ts_path"]) if paths["user_json_ts_path"] else str(paths["data_json_ts_path"]),
        "timestamped_sql_path": str(paths["user_sql_ts_path"]) if paths["user_sql_ts_path"] else str(paths["data_sql_ts_path"]),
        "backup_path": str(paths["data_json_ts_path"]),
        "backup_sql_path": str(paths["data_sql_ts_path"]),
        "app_json_path": str(paths["app_json_path"]),
        "app_sql_path": str(paths["app_sql_path"]),
        "user_json_path": str(paths["user_json_ts_path"]) if paths["user_json_ts_path"] else None,
        "user_sql_path": str(paths["user_sql_ts_path"]) if paths["user_sql_ts_path"] else None,
        "backup_dir": str(data_month_dir),
    }
