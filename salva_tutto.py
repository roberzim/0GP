#!/usr/bin/env python3
"""High‑level persistence wrapper for the 0GP application.

This module delegates the core save logic to :mod:`storage_utils`,
providing backward compatible entry points ``salva_tutto`` and
``salva_pratica``.  By funnelling all persistence through
``storage_utils.save_pratica``, the codebase avoids duplication of
common logic such as atomic file writes, path construction and
registration of SQLite adapters.  No behaviour or interface is
changed; the result dictionary returned by :func:`salva_tutto`
remains the same as in previous versions.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from storage_utils import save_pratica

def salva_tutto(pratica: Dict[str, Any], *, json_root: str = "app_pratiche", db_path: Optional[str] = None) -> Dict[str, Any]:
    """Persist a practice using the centralised storage utilities.

    This function is a thin wrapper around :func:`storage_utils.save_pratica`.
    It accepts the same arguments as the old implementation and returns
    the same result dictionary, including legacy alias keys.  No
    functional or GUI changes are introduced.

    Args:
        pratica: The practice dictionary to persist.  Must contain at
            least one of ``id_pratica``, ``id`` or ``codice``.
        json_root: Root directory for application JSON files (default
            ``"app_pratiche"``).
        db_path: Optional path to the SQLite database; if not
            specified, ``GP_DB_PATH`` or ``archivio/0gp.sqlite`` will
            be used.

    Returns:
        A dictionary describing the persistence outcome.  Keys include
        ``timestamped_path``, ``backup_path`` and a nested ``paths``
        dictionary.  See :func:`storage_utils.save_pratica` for
        details.
    """
    return save_pratica(pratica, json_root=json_root, db_path=db_path)


def salva_pratica(*args, **kwargs):
    """Legacy wrapper for ``salva_tutto``.

    This function preserves the old calling conventions where callers
    might provide an ``anagrafica_clean`` argument that should be
    ignored.  It also ensures that ``json_root`` is not passed a
    dictionary inadvertently (a common bug in earlier versions).

    Returns the same result as :func:`salva_tutto`.
    """
    pratica = None
    if args:
        pratica = args[0]
    if pratica is None:
        pratica = kwargs.pop('pratica', None)
    json_root = kwargs.pop('json_root', 'app_pratiche')
    db_path = kwargs.pop('db_path', None)
    # If json_root is accidentally a dict (e.g. anagrafica), reset it
    if isinstance(json_root, dict):
        json_root = 'app_pratiche'
    if not isinstance(pratica, dict):
        raise ValueError("salva_pratica: 'pratica' mancante o non valida (atteso dict).")
    return salva_tutto(pratica, json_root=json_root, db_path=db_path)
