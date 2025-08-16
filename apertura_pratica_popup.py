"""
This file illustrates how to modify the ``apertura_pratica_popup.py``
module to list practices directly from the SQLite database rather than
scanning the filesystem.  Adapt this code to your existing UI
components; the key change is replacing directory enumeration with a
simple query to the ``pratiche`` table.
"""

from __future__ import annotations

from nicegui import ui

from db_core import get_connection


def list_pratiche_from_db():
    conn = get_connection()
    rows = conn.execute(
        "SELECT id_pratica, data_apertura, tipo FROM pratiche ORDER BY id_pratica"
    ).fetchall()
    conn.close()
    return rows


def show_apertura_pratica_popup() -> None:
    """Display a popup allowing the user to select a practice from the DB."""
    pratiche = list_pratiche_from_db()
    with ui.dialog() as dialog:
        ui.label('Apri pratica da DB').style('font-weight: bold')
        for row in pratiche:
            pid = row['id_pratica']
            descr = f"{pid} — {row['tipo'] or ''}"
            ui.button(descr, on_click=lambda p=pid: _load_pratica(p, dialog))
    dialog.open()


def _load_pratica(pid: str, dialog) -> None:
    from repo_sqlite import load_pratica
    pratica = load_pratica(pid)
    if pratica is None:
        ui.notify(f'Pratica {pid} non trovata', color='negative')
    else:
        # TODO: integrate with your app state to display the selected
        # practice in the UI.  For now we just show a notification.
        ui.notify(f'Pratica {pid} caricata', color='positive')
    dialog.close()