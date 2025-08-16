from repo import write_pratica
# LEGACY-CLEANUP: sostituito save_* con write_pratica; valutare dual_save(...) dopo il salvataggio canonico.

from __future__ import annotations
import os, json, hashlib, sqlite3
from pathlib import Path
from datetime import datetime
from parser_xml import parse_pratica_xml
from models import Pratica

def ensure_dir(p: Path):
    p.mkdir(parents=True, exist_ok=True)

def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def write_pratica(pratica: Pratica, dest_dir: Path) -> Path:
    ensure_dir(dest_dir)
    out = dest_dir / "pratica.json"
    with out.open("w", encoding="utf-8") as f:
        json.dump(pratica.model_dump(mode="json"), f, ensure_ascii=False, indent=2, default=str)
    return out

def ensure_index(db_path: Path):
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS pratiche (
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
    con.commit()
    con.close()

def upsert_index(db_path: Path, pratica: Pratica, json_path: Path):
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    data = json_path.read_text(encoding="utf-8")
    h = sha256_text(data)
    cur.execute("""
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
    """, (
        pratica.id_pratica,
        pratica.nome_pratica,
        pratica.settore_pratica,
        pratica.materia_pratica,
        pratica.valore_pratica,
        pratica.updated_at.isoformat(),
        str(json_path.parent),
        h,
    ))
    con.commit()
    con.close()

def migrate_folder(src_dir: Path, dest_root: Path, db_path: Path):
    ensure_index(db_path)
    xmls = list(src_dir.rglob("*.xml"))
    migrated = []
    for x in xmls:
        try:
            pratica = parse_pratica_xml(str(x))
            # destination folder suggestion: 2025-0001-[nome_sanitizzato]/
            safe_id = pratica.id_pratica.replace("/", "-")
            dest_dir = dest_root / safe_id
            json_path = write_pratica(pratica, dest_dir)
            upsert_index(db_path, pratica, json_path)
            migrated.append((str(x), str(json_path)))
        except Exception as e:
            migrated.append((str(x), f"ERROR: {e}"))
    return migrated

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Migrazione XML -> JSON + indice SQLite")
    ap.add_argument("--src", required=True, help="Cartella sorgente con XML delle pratiche")
    ap.add_argument("--dest", required=True, help="Cartella destinazione per le pratiche JSON")
    ap.add_argument("--db", required=True, help="Percorso file indice SQLite (es. indice.sqlite)")
    args = ap.parse_args()

    src = Path(args.src)
    dest = Path(args.dest)
    db = Path(args.db)

    results = migrate_folder(src, dest, db)
    for src_xml, out_res in results:
        print(f"{src_xml} -> {out_res}")
