# log_gestione_pratica.py
from __future__ import annotations
from datetime import datetime
import os
from pathlib import Path

APP_LOG_DIR = Path('logs/log_gestione_pratica')  # nella directory dell'app
APP_LOG_DIR.mkdir(parents=True, exist_ok=True)

def _riga_log(user: str, id_pratica: str, base_path: str, cliente_path: str, pratica_path: str) -> str:
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    return (
        f'[{ts}] apertura_pratica | utente="{user}" | id="{id_pratica}" | '
        f'base="{base_path}" | cliente="{cliente_path}" | pratica="{pratica_path}"'
    )

def log_apertura(user: str, id_pratica: str, base_path: str, cliente_path: str, pratica_path: str) -> None:
    riga = _riga_log(user, id_pratica, base_path, cliente_path, pratica_path)

    # 1) Log generale dell’app
    app_log_file = APP_LOG_DIR / 'log_aperture.txt'
    with app_log_file.open('a', encoding='utf-8') as f:
        f.write(riga + '\n')

    # 2) Log dentro la pratica
    pratica_log_dir = Path(pratica_path) / 'log_pratica'
    pratica_log_dir.mkdir(parents=True, exist_ok=True)
    pratica_log_file = pratica_log_dir / 'log.txt'
    with pratica_log_file.open('a', encoding='utf-8') as f:
        f.write(riga + '\n')

