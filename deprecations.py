
from __future__ import annotations

class XMLRuntimeDisabled(RuntimeError):
    pass

def carica_pratica_da_xml(*args, **kwargs):
    raise XMLRuntimeDisabled(
        "Supporto XML disattivato in runtime. Migrare i dati a JSON e usare load_pratica(...) da repo.py."
    )

def salva_tutto_xml(*args, **kwargs):
    raise XMLRuntimeDisabled(
        "Salvataggio in XML disattivato. Usare save_pratica(...) (canonico) + dual_save(...) (backup) per JSON."
    )

def importa_da_xml(*args, **kwargs):
    raise XMLRuntimeDisabled(
        "Import XML disattivato in runtime. Eseguire la migrazione una tantum e lavorare solo in JSON."
    )
