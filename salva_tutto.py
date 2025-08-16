"""
This file is a replacement for the existing ``salva_tutto.py`` in the
0GP repository.  It introduces a dual‑write mechanism that persists
practices both to the canonical JSON structure and to the new SQLite
database.  If the database transaction fails for any reason the JSON
write proceeds and the error is logged so that the UI can notify the
user.

The interface of the module remains compatible with the original
implementation: call :func:`salva_tutto(pratica_dict)` to persist a
practice.  The caller is responsible for handling any returned errors.
"""

from __future__ import annotations

import json
import os
import traceback
from typing import Any, Dict, List, Optional

from repo_sqlite import upsert_pratica
from db_core import get_connection

# NOTE: adjust this import to point to the original JSON saving helper.
# In the original project there is likely a helper like ``repo.save_pratica``
# or similar.  Here we define a simple placeholder that writes the
# practice dictionary to the expected filesystem location.


def _save_pratica_json(pratica: Dict[str, Any], base_dir: Optional[str] = None) -> None:
    """Write a practice dict to a JSON file on disk.

    This placeholder emulates the behaviour of the existing JSON
    persistence.  In the real project you should import and call the
    original function instead of this one.
    """
    if base_dir is None:
        base_dir = os.path.join(os.path.dirname(__file__), 'app_pratiche')
    os.makedirs(base_dir, exist_ok=True)
    practice_dir = os.path.join(base_dir, pratica['id_pratica'])
    os.makedirs(practice_dir, exist_ok=True)
    # Write the full practice dict to a canonical file
    with open(os.path.join(practice_dir, 'pratica.json'), 'w', encoding='utf-8') as f:
        json.dump(pratica, f, ensure_ascii=False, indent=2)


def salva_tutto(pratica: Dict[str, Any], *, json_base_dir: Optional[str] = None) -> List[str]:
    """Persist a practice both to JSON and to SQLite.

    Args:
        pratica: The practice data to be persisted.
        json_base_dir: Optional override for the base directory where
            JSON files are stored.

    Returns:
        A list of error messages encountered during database persistence.
        If empty the operation succeeded on both backends.
    """
    errors: List[str] = []
    # 1. Save to JSON first.  This remains the canonical representation.
    try:
        _save_pratica_json(pratica, base_dir=json_base_dir)
    except Exception as e:
        # Any failure here is critical because JSON is the ground truth.
        raise
    # 2. Attempt to persist to SQLite.  Failure here should not block
    # the overall save; record the exception and continue.
    try:
        conn = get_connection()
        upsert_pratica(pratica, conn=conn)
        conn.close()
    except Exception as e:
        # Log full stack trace for debugging and return message to caller
        traceback.print_exc()
        errors.append(str(e))
    return errors