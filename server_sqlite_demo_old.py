"""
This file is an illustrative patch to the existing ``server.py`` used by
the NiceGUI frontend.  It introduces new UI actions that allow the
operator to create a new practice, open an existing one from the
database, import a practice from an external ``.sqlite`` or ``.json``
file, and export the current practice to a ``.sqlite`` file.  The
functions shown here are skeletons; you should integrate them into
your existing UI layout and event handlers.

Key additions:

* ``open_from_db()`` — presents a list of practices stored in the
  database and loads the selected one.
* ``import_practice()`` — opens a file dialog and imports a practice
  according to the selected strategy (upsert/skip/fail).
* ``export_current_practice()`` — saves the current practice to a
  standalone SQLite file.

To apply these changes, merge the code below into your existing
``server.py``.  You will need to adapt the UI code to fit your
application's structure and maintain state across handlers.
"""

from __future__ import annotations

import os
from typing import List, Optional

from nicegui import ui

from db_core import get_connection
from repo_sqlite import load_pratica
from import_export_sqlite import import_pratica, export_pratica


def list_pratiche_from_db() -> List[str]:
    """Return a list of all practice identifiers stored in the database."""
    conn = get_connection()
    rows = conn.execute("SELECT id_pratica FROM pratiche ORDER BY id_pratica").fetchall()
    conn.close()
    return [row['id_pratica'] for row in rows]


def open_from_db() -> None:
    """UI handler to open a practice from the database."""
    pratiche = list_pratiche_from_db()
    with ui.dialog() as dialog:
        ui.label('Seleziona pratica da aprire').style('font-weight: bold')
        for pid in pratiche:
            ui.button(pid, on_click=lambda p=pid: _load_pratica_and_close(p, dialog))
    dialog.open()


def _load_pratica_and_close(pid: str, dialog) -> None:
    """Load the selected practice and close the dialog."""
    pratica = load_pratica(pid)
    if pratica is None:
        ui.notify(f'Impossibile caricare la pratica {pid}', color='negative')
    else:
        # TODO: propagate the loaded practice into your UI state and
        # refresh forms/tabs accordingly.  The exact mechanism depends
        # on your existing application architecture.
        ui.notify(f'Pratica {pid} caricata dal database', color='positive')
    dialog.close()


def import_practice() -> None:
    """UI handler to import a practice from a file."""
    def on_file_selected(file: str) -> None:
        try:
            if file.endswith('.sqlite'):
                # Upsert strategy by default; you may prompt the user
                import_pratica(file, strategy='upsert')
            elif file.endswith('.json'):
                # Load JSON file and persist via existing logic
                # Implementation depends on your current import flow
                pass  # TODO: implement JSON import
            ui.notify('Import completato', color='positive')
        except Exception as e:
            ui.notify(f'Errore import: {e}', color='negative')
    # Show file selection dialog (NiceGUI component)
    ui.upload(on_upload=lambda e: on_file_selected(e.name))


def export_current_practice(pratica: dict) -> None:
    """UI handler to export the currently loaded practice as a SQLite file."""
    def on_path_selected(path: str) -> None:
        try:
            export_pratica(pratica['id_pratica'], path)
            ui.notify(f'Esportazione completata: {os.path.basename(path)}', color='positive')
        except Exception as e:
            ui.notify(f'Errore export: {e}', color='negative')
    # Show save dialog (NiceGUI does not provide a native save dialog; adjust
    # this stub to suit your environment.  You may request the path via
    # an input text field or use browser download APIs.)
    with ui.dialog() as dialog:
        path_input = ui.input('Percorso file .sqlite')
        ui.button('Esporta', on_click=lambda: (on_path_selected(path_input.value), dialog.close()))
    dialog.open()