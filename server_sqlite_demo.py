#!/usr/bin/env python3
from __future__ import annotations
import os, sqlite3
from nicegui import ui
from db_core import initialize_schema, get_connection
import repo_sqlite

DB_PATH = os.environ.get('GP_DB_PATH', os.path.join('archivio','0gp.sqlite'))
initialize_schema(DB_PATH, schema_path='db_schema.sql')

@ui.page('/')
def index():
    with ui.card().classes('max-w-3xl m-auto mt-10 p-4'):
        ui.label('0GP - Demo SQLite').classes('text-2xl font-bold')
        with ui.row().classes('mt-2'):
            ui.button('Elenco pratiche', on_click=show_pratiche)
        ui.label(f'DB: {DB_PATH}').classes('text-xs opacity-70 mt-2')

def show_pratiche():
    with ui.dialog() as dialog, ui.card():
        ui.label('Pratiche').classes('text-lg font-semibold')
        with ui.column().classes('max-h-96 overflow-auto w-[600px]'):
            with get_connection(DB_PATH) as con:
                con.row_factory = sqlite3.Row
                for r in con.execute("SELECT id_pratica, anno, numero, tipo_pratica, referente_nome FROM pratiche ORDER BY updated_at DESC, id_pratica DESC LIMIT 200"):
                    with ui.row().classes('justify-between w-full'):
                        ui.label(r['id_pratica'])
                        ui.label(r['tipo_pratica'] or '-')
                        ui.label(r['referente_nome'] or '-')
        ui.button('Chiudi', on_click=dialog.close).classes('mt-2')
    dialog.open()

ui.run(title='0GP Demo', reload=False, port=int(os.environ.get('PORT', '8080')), show=False)
