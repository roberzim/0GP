from __future__ import annotations
import os, json, sqlite3, hashlib
from pathlib import Path
from datetime import datetime
from typing import Tuple

SKIP_DIRS = {".git", ".hg", ".svn", ".venv", "venv", "node_modules", "__pycache__"}

def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def _open_db(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    # performance e sicurezza ragionevoli per uso locale
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA synchronous=NORMAL;")
    con.execute("PRAGMA foreign_keys=ON;")
    return con

def ensure_index(db_path: Path) -> None:
    with _open_db(db_path) as con:
        cur = con.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS pratiche(
                id TEXT PRIMARY KEY,
                nome TEXT,
                settore TEXT,
                materia TEXT,
                valore TEXT,
                updated_at TEXT,
                path TEXT,
                hash TEXT
            );
        """)
        # indici utili per ricerche/filtri
        cur.execute("CREATE INDEX IF NOT EXISTS idx_pratiche_nome    ON pratiche(nome);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_pratiche_settore ON pratiche(settore);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_pratiche_materia ON pratiche(materia);")
        con.commit()

def _iter_pratica_json(root: Path):
    """Itera su tutti i file pratica.json, saltando directory di servizio."""
    for dirpath, dirnames, filenames in os.walk(root):
        # filtra sottodirectory rumorose in-place
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        if "pratica.json" in filenames:
            yield Path(dirpath) / "pratica.json"

def _load_pratica_json(p: Path) -> tuple[dict, str] | None:
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        # normalizza hashing con sort_keys=True per stabilità
        norm = json.dumps(data, ensure_ascii=False, sort_keys=True)
        return data, sha256_text(norm)
    except Exception as e:
        print(f"SKIP {p}: invalid json ({e})")
        return None

def _iso_from_mtime(p: Path) -> str:
    try:
        return datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds")
    except Exception:
        return datetime.now().isoformat(timespec="seconds")

def reindex(root: Path, db_path: Path, purge: bool = False) -> Tuple[int, int]:
    """Indicizza tutte le pratiche JSON in SQLite.
    Ritorna (insert_count, update_count).
    """
    ensure_index(db_path)
    inserted_cnt = updated_cnt = 0

    with _open_db(db_path) as con:
        cur = con.cursor()
        if purge:
            cur.execute("DELETE FROM pratiche;")

        upsert_sql = """
            INSERT INTO pratiche (id, nome, settore, materia, valore, updated_at, path, hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                nome=excluded.nome,
                settore=excluded.settore,
                materia=excluded.materia,
                valore=excluded.valore,
                updated_at=excluded.updated_at,
                path=excluded.path,
                hash=excluded.hash
            ;
        """

        for p in _iter_pratica_json(root):
            loaded = _load_pratica_json(p)
            if not loaded:
                continue
            data, h = loaded
            idp      = (data.get("id_pratica") or "").strip()
            if not idp:
                print(f"SKIP {p}: id_pratica mancante")
                continue
            nome     = (data.get("nome_pratica") or None)
            settore  = (data.get("settore_pratica") or None)
            materia  = (data.get("materia_pratica") or None)
            valore   = (data.get("valore_pratica") or None)
            updated_ts = (data.get("updated_at") or _iso_from_mtime(p))
            pathstr  = str(p.parent)

            # verifica se esiste già e se l'hash cambia
            cur.execute("SELECT hash FROM pratiche WHERE id=?", (idp,))
            row = cur.fetchone()
            existed = row is not None
            old_hash = row[0] if existed else None

            cur.execute(upsert_sql, (idp, nome, settore, materia, valore, updated_ts, pathstr, h))
            if existed:
                if old_hash != h:
                    updated_cnt += 1
            else:
                inserted_cnt += 1

        con.commit()

    print(f"Index OK: inserite {inserted_cnt}, aggiornate {updated_cnt}")
    return inserted_cnt, updated_cnt

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Rebuild/Update indice.sqlite from pratica.json files")
    ap.add_argument("--root", required=True, type=Path, help="Root folder containing practice folders")
    ap.add_argument("--db", required=True, type=Path, help="SQLite file path to write")
    ap.add_argument("--purge", action="store_true", help="Svuota e ricrea completamente l'indice prima dell'import")
    args = ap.parse_args()
    reindex(args.root, args.db, purge=args.purge)
