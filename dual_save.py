from __future__ import annotations
from pathlib import Path
from typing import Optional, Dict, Any
import os, json, tempfile, traceback

from db_core import get_db_path, connect, transaction
import repo_sqlite
import paths
import sql_export

class DualSaveError(Exception): ...

# ---------------- I/O atomico ----------------

def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name, dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            try:
                f.flush(); os.fsync(f.fileno())
            except Exception:
                pass
        os.replace(tmp, path)
    finally:
        try: os.remove(tmp)
        except FileNotFoundError: pass

def _atomic_write_json(path: Path, data: Dict[str, Any]) -> None:
    _atomic_write(path, json.dumps(data, ensure_ascii=False, indent=2))

def _log_err(msg: str) -> None:
    try:
        lp = Path("logs") / "log_gestione_pratica"
        lp.mkdir(parents=True, exist_ok=True)
        with (lp / "dual_save_error.txt").open("a", encoding="utf-8") as f:
            f.write(msg.rstrip() + "\n")
    except Exception:
        pass

# -------------- risoluzione cartella utente --------------

def _read_user_dir_hint(app_dir: Path) -> Optional[Path]:
    hint = app_dir / "user_dir.txt"
    if hint.exists():
        try:
            p = Path(hint.read_text(encoding="utf-8").strip()).expanduser()
            p.mkdir(parents=True, exist_ok=True)
            return p
        except Exception:
            return None
    return None

def _write_user_dir_hint(app_dir: Path, user_dir: Path) -> None:
    try:
        (app_dir / "user_dir.txt").write_text(str(user_dir), encoding="utf-8")
    except Exception:
        pass

def _derive_id(data: Dict[str, Any]) -> str:
    pid = data.get("id_pratica") or data.get("id") or data.get("codice")
    if not pid:
        raise DualSaveError("Pratica senza 'id_pratica'")
    return str(pid)

# ---------------- API principale ----------------

def save_all(data: Dict[str, Any], json_path: Optional[str] = None) -> Dict[str, str]:
    """
    Pipeline:
      1) JSON primario app: app_pratiche/<id>/pratica.json (compat)
      2) Upsert SQLite
      3) Copie:
         - APP (statiche, sovrascrivibili): <id>_gp.json + <id>_gp.sql
         - UTENTE (timestamped):            <id>_gp_<DDMMYYYY>_<HHMMSS>.json + .sql
    """
    pid = _derive_id(data)
    ts = paths.timestamp_now()

    app_dir = paths.app_pratica_dir(pid)            # app_pratiche/<id>/
    # 1st choice: dato in pratica -> 2nd: hint salvato -> 3rd: env/default
    user_dir = None
    try:
        user_dir = paths.get_user_root(data)
    except Exception:
        user_dir = None
    if user_dir is None or not isinstance(user_dir, Path):
        hint = _read_user_dir_hint(app_dir)
        user_dir = hint if hint is not None else paths.get_user_root({})

    sqlite_path = Path(get_db_path())

    # 1) JSON primario compat
    primary_json = app_dir / "pratica.json"
    _atomic_write_json(primary_json, data)

    # 2) DB
    with connect(str(sqlite_path)) as conn:
        with transaction(conn):
            repo_sqlite.upsert_pratica(conn, data)
        # SQL singola pratica
        sql_text = sql_export.render_pratica_sql(conn, pid)

    # 3) Copie richieste
    try:
        # Nomi
        fname_json_ts = paths.build_timestamp_name(pid, "json", ts)
        fname_sql_ts  = paths.build_timestamp_name(pid, "sql", ts)
        fname_json_static = paths.build_static_name(pid, "json")
        fname_sql_static  = paths.build_static_name(pid, "sql")

        # APP: statici sovrascrivibili
        _atomic_write_json(app_dir / fname_json_static, data)
        _atomic_write(app_dir / fname_sql_static,  sql_text)

        # UTENTE: timestamped
        user_dir.mkdir(parents=True, exist_ok=True)
        _atomic_write_json(user_dir / fname_json_ts, data)
        _atomic_write(user_dir / fname_sql_ts,  sql_text)

        # Ricorda la cartella utente per i salvataggi futuri
        _write_user_dir_hint(app_dir, user_dir)

    except Exception as e:
        _log_err(f"[dual_save secondary files] {e}\n{traceback.format_exc()}")

    return {
        "json_primary": str(primary_json),
        "sqlite_path": str(sqlite_path),
        "user_dir": str(user_dir),
        "app_dir": str(app_dir),
        "user_json_timestamped": str(user_dir / fname_json_ts),
        "user_sql_timestamped":  str(user_dir / fname_sql_ts),
        "app_json_static":       str(app_dir / fname_json_static),
        "app_sql_static":        str(app_dir / fname_sql_static),
    }

# ------- Shim legacy: mantenere chiavi attese ('timestamped_path', 'backup_path') -------

from pathlib import Path as _P
import json as _json

def dual_save(pratica_folder, backup_dir=None, base_id=None, *, data=None, json_text=None, timestamp=None):
    """
    Legacy: ritorna anche 'timestamped_path' (JSON con TS) e 'backup_path' (JSON statico in app).
    """
    try:
        # Recupera dati se non passati
        if data is None:
            if json_text is not None:
                data = _json.loads(json_text)
            elif pratica_folder:
                p = _P(pratica_folder) / "pratica.json"
                data = _json.loads(p.read_text(encoding="utf-8"))
        if data is None:
            raise DualSaveError("dual_save legacy: dati pratica mancanti")

        res = save_all(data)
        # Compat: puntiamo il timestamped nella CARTELLA UTENTE e il backup allo statico APP
        res["timestamped_path"] = res.get("user_json_timestamped") or ""
        res["backup_path"] = res.get("app_json_static") or ""
        return res
    except Exception as e:
        raise DualSaveError(f"dual_save legacy fallito: {e}") from e
