"""Importatore SQL per pratiche.

Questo modulo espone una funzione `import_sql` che applica uno script
SQL generato dall'export del progetto a un database SQLite esistente.

L'import è idempotente: per ogni tabella toccata lo script deve
contenere un `DELETE` seguito da `INSERT`, come previsto dall'export.
Le righe di commento (che iniziano con `--`) vengono ignorate prima
di eseguire lo script. Tutte le istruzioni vengono eseguite in una
transazione; in caso di errore la transazione viene annullata e
l'eccezione propagata.

Esempio d'uso:

    from tools.import_sql import import_sql
    stats = import_sql('archivio/0gp.sqlite', 'pratica_16_2025.sql')
    print(stats['changes'], stats['tables'])

Il dizionario restituito contiene il numero totale di cambiamenti
registrati sulla connessione SQLite e l'elenco delle tabelle toccate.
"""

from __future__ import annotations

import os
import re
import sqlite3
from typing import List, Dict, Any, Tuple


def _parse_tables(sql_text: str) -> List[str]:
    """Estrae i nomi delle tabelle coinvolte da INSERT e DELETE.

    Esegue una semplice analisi delle prime parole dopo INSERT INTO
    oppure DELETE FROM. Restituisce un elenco di nomi univoci
    normalizzati (ma preserva l'ordine di apparizione).
    """
    found: List[str] = []
    for line in sql_text.splitlines():
        line = line.strip()
        if not line or line.startswith("--"):
            continue
        m = re.match(r"(?:INSERT\s+INTO|DELETE\s+FROM)\s+[`\"]?([A-Za-z0-9_]+)[`\"]?", line, re.IGNORECASE)
        if m:
            t = m.group(1)
            if t not in found:
                found.append(t)
    return found


def import_sql(db_path: str, sql_path: str) -> Dict[str, Any]:
    """Applica uno script SQL a un database SQLite.

    Args:
        db_path: percorso del file SQLite di destinazione.
        sql_path: percorso del file `.sql` da importare.

    Returns:
        Un dict con le chiavi:
            - 'changes': numero di cambiamenti effettuati sul DB.
            - 'tables': lista delle tabelle toccate.

    Raises:
        FileNotFoundError: se il DB o il file SQL non esistono.
        sqlite3.DatabaseError: se l'esecuzione dello script fallisce.
    """
    # Verifica esistenza file DB e file SQL
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Database non trovato: {db_path}")
    if not os.path.exists(sql_path):
        raise FileNotFoundError(f"File SQL non trovato: {sql_path}")

    # Leggi file SQL, filtrando commenti
    with open(sql_path, "r", encoding="utf-8") as f:
        raw_lines = f.readlines()
    # Conserva solo le righe che non sono commenti (iniziano con --)
    filtered_lines: List[str] = []
    for ln in raw_lines:
        if not ln.lstrip().startswith("--"):
            filtered_lines.append(ln.rstrip("\n"))
    sql_text = "\n".join(filtered_lines)

    # Analizza le tabelle interessate
    touched = _parse_tables(sql_text)

    # Esegui lo script in una transazione
    con = sqlite3.connect(db_path)
    try:
        con.row_factory = sqlite3.Row
        before_changes = con.total_changes
        with con:
            con.executescript(sql_text)
        after_changes = con.total_changes
        return {
            'changes': after_changes - before_changes,
            'tables': touched,
        }
    except Exception as exc:
        # rollback avviene automaticamente uscendo dal contesto se impostato isolation_level=None
        con.rollback()
        raise exc
    finally:
        con.close()
