"""Test automatizzati per la persistenza delle pratiche.

Questo modulo contiene tre test che verificano la corretta gestione
dei salvataggi in tre formati diversi:

* JSON: serializzazione e deserializzazione di una pratica su disco.
* DB SQLite: inserimento e caricamento attraverso il livello
  ``repo_sqlite``.
* SQL: export di una pratica in un file .sql, eliminazione dal DB
  e successivo import tramite la funzione ``import_sql``.

I test utilizzano esclusivamente lo standard library e i moduli del
progetto. Per eseguire i test è possibile usare pytest oppure lo
script ``run_tests.py`` fornito nella patch.
"""

from __future__ import annotations

import os
import json
import tempfile
from pathlib import Path

# Non è necessario pytest: i test sono eseguibili anche con unittest.

# Import moduli del progetto: usiamo import relativi per evitare conflitti
from repo import write_pratica
from repo import load_pratica as load_pratica_json  # Pydantic wrapper
from repo_sqlite import upsert_pratica, load_pratica as load_pratica_db
from db_core import initialize_schema, get_connection
from sql_export import render_pratica_sql
from tools.import_sql import import_sql
from db_migrations import run_migrations
import sqlite3

# Import unittest per compatibilità con run_tests.py
import unittest


def _make_pratica_dict(*, pid: str, anno: int, numero: int, include_avv: bool = True, include_scad: bool = True) -> dict:
    """Crea un dict rappresentante una pratica con campi minimi.

    Args:
        pid: Identificativo naturale della pratica (formato es. "1/2025").
        anno: Anno numerico della pratica.
        numero: Numero progressivo.
        include_avv: se True, include almeno un avvocato.
        include_scad: se True, include almeno una scadenza.

    Returns:
        Un dizionario con i campi necessari per il salvataggio.
    """
    d: dict = {
        'id_pratica': pid,
        'anno': anno,
        'numero': numero,
        'tipo_pratica': 'Test',
        'settore': None,
        'materia': None,
        'referente_email': 'ref@example.com',
        'referente_nome': 'Referente',
        'preventivo': False,
        'note': 'nota di test',
    }
    if include_avv:
        d['avvocati'] = [
            {
                'uid': 'a1',
                'email': 'avv1@example.com',
                'nome': 'Avv 1',
                'ruolo': 'referente',
            },
        ]
    if include_scad:
        d['scadenze'] = [
            {
                'uid': 's1',
                'data_scadenza': '2025-09-01',
                'descrizione': 'Test scadenza',
                'note': '',
                'completata': False,
            },
        ]
    return d


def test_json_roundtrip() -> None:
    """Verifica che una pratica salvata in JSON venga correttamente riscritta e riletta."""
    prat = _make_pratica_dict(pid='99/2025', anno=2025, numero=99)
    with tempfile.TemporaryDirectory() as d:
        temp_dir = Path(d)
        saved_path = write_pratica(folder=temp_dir, data=prat)
        assert saved_path.exists(), "Il file JSON non è stato creato"
        # Rileggi il contenuto e confronta campi chiave
        data = json.loads(saved_path.read_text(encoding='utf-8'))
        assert data['id_pratica'] == prat['id_pratica']
        assert data['anno'] == prat['anno']
        assert data['numero'] == prat['numero']
        # Verifica che le liste eventuali siano presenti
        assert isinstance(data.get('avvocati', []), list)
        assert isinstance(data.get('scadenze', []), list)


def test_db_upsert_and_load() -> None:
    """Verifica inserimento e caricamento di una pratica nel DB SQLite."""
    with tempfile.TemporaryDirectory() as d:
        db_file = Path(d) / 'test.sqlite'
        initialize_schema(str(db_file))
        prat = _make_pratica_dict(pid='1/2025', anno=2025, numero=1)
        with get_connection(str(db_file)) as con:
            upsert_pratica(con, prat)
            # Carica nuovamente
            loaded = load_pratica_db(prat['id_pratica'], conn=con)
        assert loaded is not None, "La pratica non è stata caricata dal DB"
        assert loaded['id_pratica'] == prat['id_pratica']
        # Verifica che esista almeno la stessa quantità di scadenze
        assert len(loaded.get('scadenze', [])) == len(prat.get('scadenze', []))


# =============================================================================
# Classe di test per supporto unittest
# =============================================================================
class TestSalvataggi(unittest.TestCase):
    """Wrapper che riproduce i test definiti come funzioni in metodi unittest."""

    def test_json_roundtrip(self) -> None:
        prat = _make_pratica_dict(pid='99/2025', anno=2025, numero=99)
        with tempfile.TemporaryDirectory() as d:
            temp_dir = Path(d)
            saved_path = write_pratica(folder=temp_dir, data=prat)
            self.assertTrue(saved_path.exists(), "Il file JSON non è stato creato")
            data = json.loads(saved_path.read_text(encoding='utf-8'))
            self.assertEqual(data['id_pratica'], prat['id_pratica'])
            self.assertEqual(data['anno'], prat['anno'])
            self.assertEqual(data['numero'], prat['numero'])
            self.assertIsInstance(data.get('avvocati', []), list)
            self.assertIsInstance(data.get('scadenze', []), list)

    def test_db_upsert_and_load(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            db_file = Path(d) / 'test.sqlite'
            # Usa schema_path esplicito poiché initialize_schema cerca db_schema.sql nella cwd
            schema_file = Path(__file__).resolve().parents[1] / 'db_schema.sql'
            initialize_schema(str(db_file), schema_path=str(schema_file))
            # Applica migrazioni per aggiungere uid/pos alle tabelle figlie
            run_migrations(str(db_file))
            prat = _make_pratica_dict(pid='1/2025', anno=2025, numero=1)
            with get_connection(str(db_file)) as con:
                upsert_pratica(con, prat)
            # Verifica direttamente sulla tabella pratiche e scadenze
            import sqlite3 as _sql
            with _sql.connect(str(db_file)) as con_sql:
                cur = con_sql.execute("SELECT id_pratica FROM pratiche WHERE id_pratica=?", (prat['id_pratica'],))
                row = cur.fetchone()
                self.assertIsNotNone(row, "La pratica non è presente in pratiche")
                cur = con_sql.execute("SELECT COUNT(*) FROM scadenze WHERE id_pratica=?", (prat['id_pratica'],))
                count = cur.fetchone()[0]
                self.assertEqual(count, len(prat.get('scadenze', [])))

    def test_sql_export_import(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            db_file = Path(d) / 'test2.sqlite'
            schema_file = Path(__file__).resolve().parents[1] / 'db_schema.sql'
            initialize_schema(str(db_file), schema_path=str(schema_file))
            run_migrations(str(db_file))
            prat = _make_pratica_dict(pid='2/2025', anno=2025, numero=2, include_avv=False, include_scad=True)
            with get_connection(str(db_file)) as con:
                upsert_pratica(con, prat)
                sql_str = render_pratica_sql(con, prat['id_pratica'])
            sql_path = Path(d) / 'export.sql'
            sql_path.write_text(sql_str, encoding='utf-8')
            with get_connection(str(db_file)) as con:
                for table in ['documenti', 'scadenze', 'attivita', 'pratica_avvocati', 'pratica_tariffe', 'pratiche']:
                    con.execute(f"DELETE FROM {table} WHERE id_pratica=?", (prat['id_pratica'],))
            stats = import_sql(str(db_file), str(sql_path))
            self.assertGreaterEqual(stats['changes'], 1)
            # Verifica direttamente sulla tabella pratiche e scadenze
            import sqlite3 as _sql
            with _sql.connect(str(db_file)) as con_sql:
                cur = con_sql.execute("SELECT id_pratica FROM pratiche WHERE id_pratica=?", (prat['id_pratica'],))
                row = cur.fetchone()
                self.assertIsNotNone(row, "La pratica non è stata reimportata dal SQL")
                cur = con_sql.execute("SELECT COUNT(*) FROM scadenze WHERE id_pratica=?", (prat['id_pratica'],))
                count = cur.fetchone()[0]
                self.assertEqual(count, len(prat.get('scadenze', [])))


# Nota: questa funzione era un test legacy per pytest. I test vengono ora
# eseguiti tramite la classe TestSalvataggi. La lasciamo come helper
# privato per eventuali riferimenti futuri, ma non sarà eseguita
# automaticamente (nome non inizia con 'test_').
def _legacy_test_sql_export_import() -> None:
    pass