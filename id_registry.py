"""
This is a modified version of the existing ``id_registry.py`` module to
support generating sequential practice identifiers using the SQLite
``id_counter`` table.  It falls back to reading from the old JSON
counter for historical compatibility.  The public API remains the
same as before: call :func:`next_id` with an integer year and it will
return a string like ``"8_2025"``.

To apply this change in your project, replace the original
``id_registry.py`` with this file.
"""

from __future__ import annotations

import json
import os
from typing import Optional

from db_core import get_connection, atomic_tx

# Path to the legacy JSON id registry; adjust if different in your repo
JSON_ID_REGISTRY = os.path.join(os.path.dirname(__file__), 'lib_json', 'id_pratiche.json')


def next_id(anno: int, *, conn: Optional[object] = None) -> str:
    """Return the next available practice identifier for the given year.

    This function uses the SQLite ``id_counter`` table to atomically
    allocate sequential identifiers per year.  If the year does not yet
    exist in the table, it is initialised using the last value found in
    the legacy JSON file (if it exists) or zero.  It then increments the
    counter and returns a string of the form ``"<n>_<anno>"``.

    Args:
        anno: The year for which to generate an ID (e.g. 2025).
        conn: Optional existing SQLite connection.

    Returns:
        A string representing the next available ID (e.g. ``"9_2025"``).
    """
    should_close = False
    if conn is None:
        conn = get_connection()
        should_close = True
    with atomic_tx(conn):
        row = conn.execute("SELECT last_n FROM id_counter WHERE anno = ?", (anno,)).fetchone()
        if row is None:
            # Determine starting value from JSON if available
            start_n = 0
            if os.path.exists(JSON_ID_REGISTRY):
                with open(JSON_ID_REGISTRY, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                # keys are like "8_2025"; filter those matching the year
                values = [int(k.split('_')[0]) for k in data.keys() if k.endswith(str(anno))]
                if values:
                    start_n = max(values)
            conn.execute("INSERT INTO id_counter (anno, last_n) VALUES (?, ?)", (anno, start_n))
            current_n = start_n + 1
            conn.execute("UPDATE id_counter SET last_n = ? WHERE anno = ?", (current_n, anno))
        else:
            current_n = row['last_n'] + 1
            conn.execute("UPDATE id_counter SET last_n = ? WHERE anno = ?", (current_n, anno))
        new_id = f"{current_n}_{anno}"
    if should_close:
        conn.close()
    return new_id