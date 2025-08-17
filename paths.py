from __future__ import annotations
import os
from pathlib import Path
from datetime import datetime
from typing import Any, Optional

def timestamp_now() -> str:
    return datetime.now().strftime("%d%m%Y_%H%M%S")

def build_timestamp_name(id_pratica: str, ext: str, ts: Optional[str] = None) -> str:
    ts = ts or timestamp_now()
    ext = ext.lstrip(".")
    return f"{id_pratica}_gp_{ts}.{ext}"

def build_static_name(id_pratica: str, ext: str) -> str:
    ext = ext.lstrip(".")
    return f"{id_pratica}_gp.{ext}"

def get_user_root(pratica: Optional[dict[str, Any]] = None) -> Path:
    # 1) guardo nella pratica
    if isinstance(pratica, dict):
        for k in ("user_dir", "cartella_utente", "percorso_cartella", "folder", "dir", "root_user_path"):
            v = pratica.get(k)
            if isinstance(v, str) and v.strip():
                p = Path(v).expanduser()
                p.mkdir(parents=True, exist_ok=True)
                return p
    # 2) env
    env_p = os.environ.get("GP_USER_DIR")
    if env_p:
        p = Path(env_p).expanduser()
        p.mkdir(parents=True, exist_ok=True)
        return p
    # 3) default Documenti/Pratiche
    p = Path.home() / "Documenti" / "Pratiche"
    p.mkdir(parents=True, exist_ok=True)
    return p

def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)

def app_pratica_dir(id_pratica: str) -> Path:
    p = Path("app_pratiche") / id_pratica
    p.mkdir(parents=True, exist_ok=True)
    return p
