# --- Retro-compat per apertura_pratica_popup.py (JSON + SQLite) ---
from datetime import date
from pathlib import Path
import os, json
from db_core import get_connection

def load_next_id():
    """
    Restituisce (prossimo_numero, anno_corrente).
    Priorità: SQLite(id_counter) -> SQLite(pratiche.max(numero)) -> lib_json/id_pratiche.json -> (1, anno)
    """
    anno = date.today().year
    db_path = os.environ.get('GP_DB_PATH', os.path.join('archivio', '0gp.sqlite'))

    # 1) Prova su SQLite: id_counter
    try:
        with get_connection(db_path) as con:
            try:
                row = con.execute("SELECT last_n FROM id_counter WHERE anno=?", (anno,)).fetchone()
            except Exception:
                row = None
            if row:
                return int(row[0]) + 1, anno
            # 2) Fallback: pratiche
            try:
                r2 = con.execute("SELECT MAX(numero) FROM pratiche WHERE anno=?", (anno,)).fetchone()
                maxn = int(r2[0]) if r2 and r2[0] is not None else 0
                return maxn + 1, anno
            except Exception:
                pass
    except Exception:
        pass

    # 3) Ultimo fallback: JSON storico
    try:
        p = Path('lib_json') / 'id_pratiche.json'
        if p.exists():
            data = json.loads(p.read_text(encoding='utf-8'))
            maxn = 0
            for el in data if isinstance(data, list) else []:
                try:
                    a = int(str(el.get('anno_pratica') or '0'))
                    if a == anno:
                        n = int(str(el.get('num_pratica') or '0'))
                        if n > maxn:
                            maxn = n
                except Exception:
                    continue
            return maxn + 1, anno
    except Exception:
        pass

    return 1, anno

def persist_after_save(num: int, anno: int, nome_pratica: str, percorso_pratica: str, created_by: str | None = None):
    """
    Aggiorna SQLite(id_counter) e sincronizza lib_json/id_pratiche.json
    per compatibilità con l’elenco pratiche della UI.
    """
    db_path = os.environ.get('GP_DB_PATH', os.path.join('archivio', '0gp.sqlite'))

    # 1) Aggiorna id_counter su SQLite (se disponibile)
    try:
        with get_connection(db_path) as con:
            try:
                con.execute("""
                    INSERT INTO id_counter(anno,last_n) VALUES(?,?)
                    ON CONFLICT(anno) DO UPDATE SET last_n=excluded.last_n
                """, (int(anno), int(num)))
            except Exception:
                pass
    except Exception:
        pass

    # 2) Aggiorna elenco storico JSON (usato dalla UI originale)
    try:
        lib = Path('lib_json'); lib.mkdir(parents=True, exist_ok=True)
        fp = lib / 'id_pratiche.json'
        data = []
        if fp.exists():
            try:
                data = json.loads(fp.read_text(encoding='utf-8'))
                if not isinstance(data, list):
                    data = []
            except Exception:
                data = []
        # aggiorna se presente, altrimenti append
        found = False
        for el in data:
            try:
                if int(str(el.get('num_pratica') or -1)) == int(num) and int(str(el.get('anno_pratica') or -1)) == int(anno):
                    el['nome_pratica'] = nome_pratica
                    el['percorso_pratica'] = percorso_pratica
                    el['link_cartella'] = percorso_pratica
                    found = True
                    break
            except Exception:
                continue
        if not found:
            data.append({
                'num_pratica': int(num),
                'anno_pratica': int(anno),
                'nome_pratica': nome_pratica,
                'percorso_pratica': percorso_pratica,
                'link_cartella': percorso_pratica,
            })
        tmp = fp.with_suffix('.json.tmp')
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        os.replace(tmp, fp)
    except Exception:
        pass

