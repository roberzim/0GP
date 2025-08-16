from __future__ import annotations
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent))
from models import Pratica, PersonaFisica, PersonaGiuridica, RigaTariffa, FaseProcessuale, TabellaMinisteriale, TabellaDati, TabellaMetadata
from repo import save_pratica, load_pratica
from dual_save import dual_save

def main(root: Path):
    folder = root / "1-2025"
    folder.mkdir(parents=True, exist_ok=True)
    demo = Pratica(
        id_pratica="1/2025",
        nome_pratica="Ricorso TAR - Cliente X",
        data_apertura="2025-08-11",
        valore_pratica="50000",
        tipo_pratica="Contenzioso",
        settore_pratica="Tecnologia",
        materia_pratica="Civile",
        tipo_tariffe=["Base", "Tabelle ministeriali"],
        avvocato_referente="Claudio Palmieri",
        avvocato_in_mandato="Claudio Palmieri & Chiara Cremona",
        preventivo_inviato=True,
    )
    demo.anagrafica_imprese.append(PersonaGiuridica(
        Posizione="Cliente",
        Denominazione="The Innovation Lawyers S.L.A.",
        Cod_fisc="18187271004",
        P_IVA="18187271004",
        Indirizzo_legale="Via Properzio, 5, 00193 Roma",
        Email="info@theinnovationlawyers.eu"
    ))
    demo.anagrafica_persone.append(PersonaFisica(
        Nome="Chiara",
        Cognome="Cremona",
        Cod_fisc="CRMCHR75M52L319K",
        Indirizzo_lavoro="Via Properzio 5, Roma",
        Email="chiara.cremona@theinnovationlawyers.eu",
        Posizione="avvocato_TiL"
    ))
    demo.contenzioso.tariffe.append(RigaTariffa(tipo="Base", note="Onorario base", tot=300.0))
    demo.contenzioso.tariffe.append(RigaTariffa(tipo="Oraria", note="Studio atti", tariffa_oraria=250.0, tempo_stimato_min=120, tot=500.0))
    meta = TabellaMetadata(data="2025-08-11", ambito="TAR Lazio", scaglione="52000.01-260000.00")
    dati = TabellaDati(
        fasi={
            "Studio": FaseProcessuale(valore_medio=2000.0, compenso=2000.0),
            "Introduzione": FaseProcessuale(valore_medio=3000.0, compenso=3000.0)
        },
        prospetto={
            "Compenso tabellare": 5000.0,
            "Spese generali (15%)": 750.0,
            "IVA (22%)": 1265.0
        },
        totale_documento=7015.0
    )
    demo.preventivi[1] = TabellaMinisteriale(numero=1, metadata=meta, dati=dati)
    save_pratica(demo, folder, actor="demo-script")
    
    # dual-save: copia timestamp nella cartella pratica + backup app
    dual_save(pratica_folder=folder, backup_dir=Path(\"archivio/backups_json\"), base_id=demo.id_pratica)
loaded = load_pratica(folder)
    loaded.nome_pratica = "Ricorso TAR - Cliente X (aggiornato)"
    save_pratica(loaded, folder, actor="demo-script")


    # dual-save: copia timestamp nella cartella pratica + backup app (post-aggiornamento)
    dual_save(pratica_folder=folder, backup_dir=Path(\"archivio/backups_json\"), base_id=loaded.id_pratica)
if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Crea una pratica demo e scrive history.jsonl")
    ap.add_argument("--root", default=Path("archivio/pratiche"), type=Path, help="Cartella archivio pratiche")
    args = ap.parse_args()
    main(args.root)

