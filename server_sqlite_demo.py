#!/usr/bin/env python3
import os
import logging
from nicegui import ui

# Nuovo layer
from db_core import initialize_schema, get_connection

DB_PATH = os.environ.get('GP_DB_PATH', os.path.join('archivio', '0gp.sqlite'))

def bootstrap_db() -> None:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    initialize_schema(DB_PATH)
    logging.info("DB pronto: %s", DB_PATH)

@ui.page('/')
def index():
    with ui.header().classes('items-center justify-between'):
        ui.label('0GP (SQLite layer)').classes('text-lg')
        with ui.row():
            ui.button('Nuova pratica', on_click=nuova_pratica)
            ui.button('Apri da DB', on_click=apri_da_db)
            ui.button('Importa (.sqlite/.json)', on_click=do_import)
            ui.button('Esporta (.sqlite)', on_click=do_export)
    ui.label('Benvenuto in 0GP + SQLite').classes('mt-6')

def nuova_pratica():
    # TODO: collega al tuo flusso esistente di creazione pratica e poi dual-write
    ui.notify('TODO: Nuova pratica')

def apri_da_db():
    try:
        with get_connection(DB_PATH) as con:
            rows = con.execute(
                'SELECT id_pratica FROM pratiche ORDER BY id_pratica DESC'
            ).fetchall()
        if not rows:
            ui.notify('Nessuna pratica nel DB', type='warning')
            return
        with ui.dialog() as d, ui.card():
            ui.label('Pratiche in DB')
            for r in rows:
                pid = r['id_pratica'] if isinstance(r, dict) else r[0]
                ui.button(pid, on_click=lambda e, _pid=pid: (d.close(), ui.notify(f'Aperta {_pid}')))
            ui.button('Chiudi', on_click=d.close)
        d.open()
    except Exception as e:
        logging.exception('Errore apertura da DB')
        ui.notify(f'Errore: {e}', type='negative')

def do_import():
    # TODO: collega a import_export_sqlite.import_pratica_sqlite / import da JSON
    ui.notify('TODO: Import')

def do_export():
    # TODO: collega a import_export_sqlite.export_pratica_sqlite sulla pratica corrente
    ui.notify('TODO: Export')

def main():
    logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')
    bootstrap_db()
    # Avvio NiceGUI
    ui.run(title='0GP', port=int(os.environ.get('PORT', 8080)))

if __name__ in {'__main__', '__mp_main__'}:
    main()

