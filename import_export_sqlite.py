"""
import_export_sqlite.py
-----------------------

This module provides helpers for exporting and importing individual
practices as standalone SQLite databases.  The export function builds a
self‑contained database file with the same schema as the primary
database but containing only the rows related to the selected
``id_pratica``.  The import function reads a practice from such a
database and merges it into the main database, respecting the chosen
conflict strategy.

Typical usage::

    from import_export_sqlite import export_pratica, import_pratica
    export_pratica('8_2025', '/tmp/8_2025.sqlite')
    import_pratica('/tmp/8_2025.sqlite', strategy='upsert')

The conflict strategies are:

* ``'upsert'``: Insert or update the existing practice and replace all
  child collections.
* ``'skip'``: Do nothing if a practice with the same ``id_pratica``
  already exists.
* ``'fail'``: Raise an exception if a conflict would occur.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
from typing import Optional

from db_core import get_connection, initialize_schema, atomic_tx
from repo_sqlite import load_pratica, upsert_pratica


def export_pratica(id_pratica: str, dest_path: str, *, source_conn: Optional[sqlite3.Connection] = None) -> None:
    """Export a single practice to its own SQLite file.

    The resulting file will contain the full schema and only the rows
    pertaining to ``id_pratica``.  Any existing file at ``dest_path`` is
    overwritten.

    Args:
        id_pratica: Identifier of the practice to export (e.g. "8_2025").
        dest_path: Destination path for the exported SQLite file.
        source_conn: Optional existing connection to the main database.
    """
    # Ensure destination directory exists
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    # Create a new database file and apply schema
    export_conn = sqlite3.connect(dest_path)
    export_conn.row_factory = sqlite3.Row
    initialize_schema(export_conn)
    should_close = False
    if source_conn is None:
        source_conn = get_connection()
        should_close = True
    # Load the practice from the main DB and insert it into the new DB
    pratica = load_pratica(id_pratica, conn=source_conn)
    if pratica is None:
        raise ValueError(f"Practice {id_pratica} not found in the source database.")
    upsert_pratica(pratica, conn=export_conn)
    # Copy lookup tables for completeness
    # Note: you may choose to omit lookups or only include entries
    # referenced by the practice.
    for table in ('lookup_tipi_pratica', 'lookup_settori', 'lookup_materie', 'lookup_avvocati'):
        rows = source_conn.execute(f"SELECT * FROM {table}").fetchall()
        if not rows:
            continue
        cols = [desc[0] for desc in source_conn.execute(f"PRAGMA table_info({table})")]  # column names
        placeholders = ','.join('?' for _ in cols)
        for row in rows:
            export_conn.execute(
                f"INSERT OR IGNORE INTO {table} ({','.join(cols)}) VALUES ({placeholders})",
                tuple(row[c] for c in cols)
            )
    export_conn.commit()
    export_conn.close()
    if should_close:
        source_conn.close()


def import_pratica(src_path: str, *, strategy: str = 'upsert', conn: Optional[sqlite3.Connection] = None) -> None:
    """Import a practice from a standalone SQLite file into the main database.

    Args:
        src_path: Path to the SQLite file created by :func:`export_pratica`.
        strategy: Conflict resolution strategy: ``'upsert'`` (default),
            ``'skip'``, or ``'fail'``.
        conn: Optional existing connection to the main database.

    Raises:
        ValueError: If the strategy is unknown or a conflict occurs in
            ``'fail'`` mode.
    """
    if strategy not in ('upsert', 'skip', 'fail'):
        raise ValueError(f"Unknown import strategy: {strategy}")
    should_close = False
    if conn is None:
        conn = get_connection()
        should_close = True
    src_conn = sqlite3.connect(src_path)
    src_conn.row_factory = sqlite3.Row
    # Determine the ID of the practice contained in the file
    id_row = src_conn.execute("SELECT id_pratica FROM pratiche").fetchone()
    if not id_row:
        raise ValueError("Source file does not contain a practice")
    id_pratica = id_row['id_pratica']
    existing = load_pratica(id_pratica, conn=conn)
    if existing and strategy == 'skip':
        # Skip import entirely
        if should_close:
            conn.close()
        src_conn.close()
        return
    if existing and strategy == 'fail':
        src_conn.close()
        if should_close:
            conn.close()
        raise ValueError(f"Practice {id_pratica} already exists; import aborted")
    # Extract practice from source and upsert into target
    pratica = load_pratica(id_pratica, conn=src_conn)
    if pratica is None:
        raise ValueError("Could not load practice from source file")
    upsert_pratica(pratica, conn=conn)
    if should_close:
        conn.close()
    src_conn.close()