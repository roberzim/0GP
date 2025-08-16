# models.py - shim per compatibilità con repo.py
# Re-esporta Pratica dal modello pydantic esistente.
try:
    from models_pydantic import Pratica  # type: ignore
except Exception as e:
    # Se non esiste, definisci un placeholder minimale.
    from dataclasses import dataclass
    @dataclass
    class Pratica:
        id_pratica: str
        nome_pratica: str
        percorso_pratica: str
