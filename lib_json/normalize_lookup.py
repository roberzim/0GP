# tools/normalize_lookup.py
import json, sys, pathlib
MAP = {
 "avvocati.json":"avvocati","materie.json":"materie","settori.json":"settori",
 "tariffe.json":"tariffe","tipo_pratica.json":"tipo_pratica","posizioni.json":"posizioni",
 "persone_fisiche.json":"persone_fisiche","persone_giuridiche.json":"persone_giuridiche",
}
root = pathlib.Path("./lib_json")
for fname, key in MAP.items():
    p = root/fname
    if not p.exists(): 
        print("skip", p); continue
    data = json.load(open(p, encoding="utf-8"))
    if isinstance(data, list):  # array nudo → incapsula
        data = {key: data}
        json.dump(data, open(p,"w",encoding="utf-8"), ensure_ascii=False, indent=2)
        print("fixed", p)
    elif key not in data:
        raise SystemExit(f"{p} non ha la chiave '{key}'")
print("OK")

