# tools/smoke_suite_pratiche.py
# Mini suite di test per Gestione Pratiche (JSON-only)
# - Writer JSON interno (nessuna dipendenza da save_pratica_json)
# - Nomenclatura NNAAAA nei nomi file (1/2025 -> 012025, 11/2025 -> 112025)
# - Compatibile con reindex(root, db_path) usando un DB SQLite (archivio/indice.sqlite)
#
# Uso:
#   python3 tools/smoke_suite_pratiche.py --mode no-collision
#   python3 tools/smoke_suite_pratiche.py --mode overwrite
#   python3 tools/smoke_suite_pratiche.py --mode next-id
# Opzionale: --keep per lasciare il registro modificato a fine test.

from pathlib import Path
import argparse, json, time, shutil, sys, os, sqlite3
from datetime import datetime, date

# --- Fix path e cwd alla root del progetto ---
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.chdir(str(ROOT))

try:
    from id_registry import load_next_id, persist_after_save
    from reindex import reindex  # firma: reindex(root, db_path)
except Exception as e:
    print("ERRORE: impossibile importare moduli del progetto (id_registry/reindex).")
    print("Dettagli:", e)
    raise

REG_PATH = Path("lib_json/id_pratiche.json")           # registro JSON
SQLITE_DB = Path("archivio/indice.sqlite")             # indice SQLite da usare con reindex
APP_DIR = Path("app_pratiche")
BKP_DIR = Path("archivio/backups_json")
APP_DIR.mkdir(parents=True, exist_ok=True)
BKP_DIR.mkdir(parents=True, exist_ok=True)
SQLITE_DB.parent.mkdir(parents=True, exist_ok=True)

def now_ts():
    return time.strftime("%Y%m%d_%H%M%S")

def _ensure_sqlite_db_ok(db_path: Path):
    """Se esiste un file non-SQLite a db_path, lo rinomina e crea un DB nuovo."""
    if db_path.exists():
        try:
            with sqlite3.connect(db_path) as con:
                con.execute("PRAGMA user_version;").fetchone()
            return  # è un DB valido
        except Exception:
            bad = db_path.with_suffix(db_path.suffix + f".bad_{now_ts()}")
            db_path.replace(bad)
            print(f"[warn] File non-SQLite trovato in {db_path}. Rinominato in {bad}.")
    # Se non esiste o è stato rinominato, verrà creato da reindex()

def load_registry():
    return json.loads(REG_PATH.read_text(encoding="utf-8"))

def save_registry(obj):
    REG_PATH.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")

def ensure_registry_schema():
    data = load_registry()
    if not isinstance(data, dict) or "records" not in data:
        raise SystemExit("Schema registro non conforme (manca 'records'). Esegui la migrazione prima dei test.")
    return data

def id_exists_in_registry(num:int, anno:int):
    data = ensure_registry_schema()
    for r in data["records"]:
        try:
            n = int(r.get("num_pratica"))
            a = int(r.get("anno_pratica"))
        except Exception:
            continue
        if n==num and a==anno:
            return True, r.get("nome_pratica") or ""
    return False, ""

def next_id_for_year(anno:int):
    data = ensure_registry_schema()
    maxn = 0
    for r in data["records"]:
        try:
            a = int(r.get("anno_pratica"))
            if a != anno:
                continue
            n = int(r.get("num_pratica"))
            if n > maxn:
                maxn = n
        except Exception:
            continue
    return maxn + 1 if maxn>=0 else 1

def prepare_collision_for_current_next_id():
    # Crea una collisione con load_next_id() attuale, aggiungendo un record con stesso ID ma nome diverso.
    num, anno = load_next_id()
    exists, _ = id_exists_in_registry(num, anno)
    data = ensure_registry_schema()
    if not exists:
        data["records"].append({
            "id_pratica": f"{num}/{anno}",
            "num_pratica": num,
            "anno_pratica": anno,
            "nome_pratica": f"Collisione_{now_ts()}",
            "percorso_pratica": "",
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "created_by": "smoke"
        })
        save_registry(data)
    return num, anno

# ---------- Utils scrittura file ----------
def _make_id_suffix(numero: int, anno: int) -> str:
    # 1/2025 -> '012025' ; 11/2025 -> '112025'
    s = f"{numero}{anno}"
    return ('0' + s) if len(s) == 5 else s

def backup_registry():
    bak = REG_PATH.with_suffix(".json.smokebak")
    shutil.copy2(REG_PATH, bak)
    return bak

def restore_registry(backup_path:Path):
    if backup_path.exists():
        shutil.copy2(backup_path, REG_PATH)
        backup_path.unlink(missing_ok=True)

# ---------- Writer JSON interno per lo smoke ----------
def _write_pratica_json(pratica_data: dict, numero:int, anno:int):
    """Scrive:
    - app_pratiche/<NNAAAA>_gp_<YYYYmmdd_HHMMSS>.json (timestamped)
    - archivio/backups_json/<NNAAAA>_gp.json (backup canonico)
    Ritorna (path_timestamped, path_backup, suffix).
    """
    suffix = _make_id_suffix(numero, anno)
    ts = now_ts()
    ts_path = APP_DIR / f"{suffix}_gp_{ts}.json"
    ts_path.write_text(json.dumps(pratica_data, ensure_ascii=False, indent=2), encoding="utf-8")
    bkp_path = BKP_DIR / f"{suffix}_gp.json"
    bkp_path.write_text(json.dumps(pratica_data, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(ts_path), str(bkp_path), suffix

def simulate_save(id_num:int, id_anno:int, nome_pratica:str, percorso_base:str="app_pratiche"):
    # Simula il salvataggio di una pratica come fa la UI (senza UI).
    pratica_path = os.path.join(percorso_base, f"{nome_pratica}")
    os.makedirs(os.path.join(pratica_path, 'log_pratica'), exist_ok=True)
    os.makedirs(os.path.join(pratica_path, 'documenti_pratica'), exist_ok=True)
    pratica_data = {
        "id_pratica": f"{id_num}/{id_anno}",
        "nome_pratica": nome_pratica,
        "percorso_pratica": pratica_path,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    ts_json, bkp_json, suffix = _write_pratica_json(pratica_data, id_num, id_anno)
    persist_after_save(id_num, id_anno, nome_pratica, pratica_path, created_by="smoke")
    # Assicura che il file SQLite esista/valga e poi reindicizza
    _ensure_sqlite_db_ok(SQLITE_DB)
    reindex(root="archivio", db_path=SQLITE_DB)
    return pratica_data, ts_json, bkp_json, suffix

def check_outputs(suffix:str):
    bkp = BKP_DIR / f"{suffix}_gp.json"
    ts_candidates = sorted([p for p in APP_DIR.glob(f"{suffix}_gp_*.json")])
    return bkp.exists(), len(ts_candidates)>0

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["no-collision","overwrite","next-id"], required=True,
                    help="Scenario: nessuna collisione, sovrascrivi ID in collisione, usa primo ID successivo in collisione")
    ap.add_argument("--keep", action="store_true", help="Non ripristinare il registro a fine test")
    args = ap.parse_args()

    if not REG_PATH.exists():
        print("ERRORE: lib_json/id_pratiche.json non trovato")
        sys.exit(1)

    bak = backup_registry()
    print("Backup registro:", bak)

    try:
        if args.mode == "no-collision":
            num, anno = load_next_id()
            pratica_name = f"Smoke_NoCollision_{now_ts()}"
            pratica, ts_json, bkp_json, suffix = simulate_save(num, anno, pratica_name)
            ok_bkp, ok_ts = check_outputs(suffix)
            print(f"[no-collision] ID: {pratica['id_pratica']} (suffix {suffix}) backup: {ok_bkp} timestamped: {ok_ts}")

        elif args.mode == "overwrite":
            num, anno = prepare_collision_for_current_next_id()
            pratica_name = f"Smoke_Overwrite_{now_ts()}"
            pratica, ts_json, bkp_json, suffix = simulate_save(num, anno, pratica_name)
            ok_bkp, ok_ts = check_outputs(suffix)
            print(f"[overwrite] ID: {pratica['id_pratica']} (suffix {suffix}) backup: {ok_bkp} timestamped: {ok_ts}")

        elif args.mode == "next-id":
            num, anno = prepare_collision_for_current_next_id()
            new_num = next_id_for_year(anno)
            pratica_name = f"Smoke_NextID_{now_ts()}"
            pratica, ts_json, bkp_json, suffix = simulate_save(new_num, anno, pratica_name)
            ok_bkp, ok_ts = check_outputs(suffix)
            print(f"[next-id] ID: {pratica['id_pratica']} (suffix {suffix}) backup: {ok_bkp} timestamped: {ok_ts}")

        else:
            raise SystemExit("Modo non riconosciuto")

        print("File creati:", ts_json, bkp_json)
        print("OK. Controlla anche indice.sqlite aggiornato.")

    finally:
        if not args.keep:
            restore_registry(bak)
            print("Registro ripristinato dal backup.")
        else:
            print("Registro lasciato modificato (--keep).")


if __name__ == "__main__":
    main()
