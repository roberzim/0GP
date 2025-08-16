
from __future__ import annotations
import shutil, os
from pathlib import Path
from datetime import datetime

def backup_archivio(src_root: Path, dest_dir: Path, keep: int = 7) -> Path:
    """Crea uno ZIP timestamp dell'archivio JSON e applica una semplice retention (keep ultimi N)."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_path = dest_dir / f"archivio_json_{ts}.zip"
    # zip intera cartella src_root
    shutil.make_archive(str(zip_path.with_suffix('')), 'zip', root_dir=src_root)
    # retention
    zips = sorted(dest_dir.glob("archivio_json_*.zip"), reverse=True)
    for old in zips[keep:]:
        try:
            old.unlink()
        except Exception:
            pass
    print(f"Backup creato: {zip_path}")
    return zip_path

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Backup ZIP dell'archivio JSON con retention")
    ap.add_argument("--src", required=True, help="Cartella radice dell'archivio (contiene le pratiche JSON)")
    ap.add_argument("--dest", required=True, help="Cartella di destinazione dei backup .zip")
    ap.add_argument("--keep", type=int, default=7, help="Numero di backup da mantenere (default 7)")
    args = ap.parse_args()
    backup_archivio(Path(args.src), Path(args.dest), keep=args.keep)
