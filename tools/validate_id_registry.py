#!/usr/bin/env python3
# tools/validate_id_registry.py
# Valida lib_json/id_pratiche.json e segnala eventuali problemi
import json, pathlib, sys, itertools

P = pathlib.Path("./lib_json/id_pratiche.json")

def main():
    if not P.exists():
        print("ERRORE: lib_json/id_pratiche.json non trovato"); sys.exit(1)
    data = json.load(open(P, encoding="utf-8"))
    if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("records"), list):
        print("ERRORE: schema non conforme. Atteso: {'version':1,'records':[...]}")
        sys.exit(2)

    seen = set()
    errors = []
    for i, r in enumerate(data["records"], 1):
        idp = r.get("id_pratica")
        num = r.get("num_pratica"); anno = r.get("anno_pratica")
        if not idp or not isinstance(idp, str) or "/" not in idp:
            errors.append((i, "id_pratica mancante o invalido", r)); continue
        try:
            n2, a2 = idp.split("/",1); n2=int(n2); a2=int(a2)
        except Exception:
            errors.append((i, "id_pratica non numerico N/AAAA", r)); continue
        if not isinstance(num, int) or not isinstance(anno, int) or (num!=n2 or anno!=a2):
            errors.append((i, "num_pratica/anno_pratica non coerenti con id_pratica", r))
        if idp in seen:
            errors.append((i, "duplicato id_pratica", r))
        seen.add(idp)
    if errors:
        print("PROBLEMI:")
        for e in errors[:20]:
            print("-", e[0], e[1], "→", e[2])
        if len(errors) > 20:
            print(f"... e altri {len(errors)-20} errori")
        sys.exit(3)
    print("OK: id_pratiche.json conforme e coerente.")

if __name__ == "__main__":
    main()
