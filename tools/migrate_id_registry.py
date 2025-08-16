#!/usr/bin/env python3
# tools/migrate_id_registry.py
# Migra lib_json/id_pratiche.json allo schema {"version":1,"records":[...]} se necessario.
import json, time, pathlib, sys

P = pathlib.Path("./lib_json/id_pratiche.json")

def main():
    if not P.exists():
        print("ERRORE: lib_json/id_pratiche.json non trovato"); sys.exit(1)
    data = json.load(open(P, encoding="utf-8"))
    # Se già nello schema target, esci
    if isinstance(data, dict) and data.get("version") == 1 and isinstance(data.get("records"), list):
        print("Schema già conforme (version/records). Nessuna migrazione necessaria.")
        return
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    records = []
    # Caso 1: array di stringhe "N/AAAA"
    if isinstance(data, list):
        for item in data:
            if isinstance(item, str) and "/" in item:
                try:
                    num, anno = item.split("/", 1)
                    num = int(num.strip()); anno = int(anno.strip())
                except Exception:
                    print("Voce non riconosciuta:", item); continue
                records.append({
                    "id_pratica": f"{num}/{anno}",
                    "num_pratica": num,
                    "anno_pratica": anno,
                    "nome_pratica": "",
                    "percorso_pratica": "",
                    "created_at": now,
                    "created_by": None
                })
    # Caso 2: dict legacy con chiavi diverse
    elif isinstance(data, dict):
        # Proviamo a dedurre da chiavi comuni
        # Esempio atteso: {"ultimo_numero": 17, "anno": 2025, "storico": ["1/2025","2/2025",...]}
        storico = []
        if "records" in data and isinstance(data["records"], list):
            # Forziamo mappa di chiavi più compatibile
            for r in data["records"]:
                if isinstance(r, dict) and ("id_pratica" in r or ("num_pratica" in r and "anno_pratica" in r)):
                    idp = r.get("id_pratica")
                    num = r.get("num_pratica")
                    anno = r.get("anno_pratica")
                    if idp and isinstance(idp, str) and "/" in idp:
                        try:
                            n2, a2 = idp.split("/",1); n2=int(n2); a2=int(a2)
                        except Exception:
                            continue
                        records.append({
                            "id_pratica": idp, "num_pratica": n2, "anno_pratica": a2,
                            "nome_pratica": r.get("nome_pratica",""),
                            "percorso_pratica": r.get("percorso_pratica",""),
                            "created_at": r.get("created_at", now),
                            "created_by": r.get("created_by", None)
                        })
                    elif isinstance(num, int) and isinstance(anno, int):
                        records.append({
                            "id_pratica": f"{num}/{anno}", "num_pratica": num, "anno_pratica": anno,
                            "nome_pratica": r.get("nome_pratica",""),
                            "percorso_pratica": r.get("percorso_pratica",""),
                            "created_at": r.get("created_at", now),
                            "created_by": r.get("created_by", None)
                        })
        elif "storico" in data and isinstance(data["storico"], list):
            storico = data["storico"]
            for s in storico:
                if isinstance(s, str) and "/" in s:
                    try:
                        num, anno = s.split("/",1); num=int(num); anno=int(anno)
                    except Exception:
                        continue
                    records.append({
                        "id_pratica": f"{num}/{anno}",
                        "num_pratica": num,
                        "anno_pratica": anno,
                        "nome_pratica": "",
                        "percorso_pratica": "",
                        "created_at": now,
                        "created_by": None
                    })
        else:
            print("Formato legacy non riconosciuto, fallback a copia conforme minima.")
            # Proviamo ad inferire ultimo numero/anno
            ultimo = int(data.get("ultimo_numero", 0)) if "ultimo_numero" in data else 0
            anno = int(data.get("anno", time.localtime().tm_year))
            for i in range(1, ultimo+1):
                records.append({
                    "id_pratica": f"{i}/{anno}",
                    "num_pratica": i,
                    "anno_pratica": anno,
                    "nome_pratica": "",
                    "percorso_pratica": "",
                    "created_at": now,
                    "created_by": None
                })
    else:
        print("Formato di id_pratiche.json non gestito. Annullato."); sys.exit(2)

    out = {"version": 1, "records": records}
    # Backup file originale
    backup = P.with_suffix(".json.bak")
    with open(backup, "w", encoding="utf-8") as fb:
        json.dump(data, fb, ensure_ascii=False, indent=2)
    with open(P, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"Migrazione completata. Backup: {backup}  ->  Target: {P}")

if __name__ == "__main__":
    main()
