# materia_settore_popup_def.py — versione JSON-only
from __future__ import annotations
from pathlib import Path
import json

from nicegui import ui
from utils import stile_popup, crea_pulsanti_controllo

# Se disponibili, usa le funzioni di utilità; altrimenti fallback su file JSON
try:
    from utils_lookup import load_materie as _load_materie_util
except Exception:
    _load_materie_util = None  # type: ignore

try:
    from utils_lookup import load_settori as _load_settori_util
except Exception:
    _load_settori_util = None  # type: ignore

MATERIE_JSON = Path('lib_json/materie.json')
SETTORI_JSON = Path('lib_json/settori.json')


# --------- Helper JSON generici ---------

def _read_list_from_json(path: Path, key: str) -> list[str]:
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        if isinstance(data, dict):
            lst = data.get(key, [])
        elif isinstance(data, list):
            lst = data
        else:
            lst = []
        return [s for s in lst if isinstance(s, str) and s.strip()]
    except Exception:
        return []


def _save_list_to_json(path: Path, key: str, items: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {key: sorted({s.strip() for s in items if isinstance(s, str) and s.strip()})}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')


# --------- Materie ---------

def _load_materie() -> list[str]:
    # Preferisci utilità centralizzata se presente
    if _load_materie_util:
        try:
            return sorted({s.strip() for s in _load_materie_util() if isinstance(s, str) and s.strip()})
        except Exception:
            pass
    # Fallback al file
    return sorted({s.strip() for s in _read_list_from_json(MATERIE_JSON, 'materie')})


def _save_materie(items: list[str]) -> None:
    _save_list_to_json(MATERIE_JSON, 'materie', items)


def mostra_popup_modifica_materie(on_update=None):
    stile_popup()  # Applica stile globale

    rows = [{'name': i} for i in _load_materie()]

    dialog = ui.dialog().classes('w-full max-w-[95vw]')
    with dialog, ui.card().classes('popup-card min-w-[600px]') as card:
        ui.label('Gestione Materie').classes('popup-header')
        with ui.row():
            with ui.column().style('min-width: 300px'):
                table = ui.table(
                    columns=[{'name': 'name', 'label': 'Materia', 'field': 'name', 'sortable': True}],
                    rows=rows, row_key='name', selection='single'
                )
            with ui.column().style('min-width: 300px'):
                input_name = ui.input(label='Nome materia', placeholder='Inserisci nome...')

                def aggiorna():
                    table.update()
                    try:
                        _save_materie([r['name'] for r in rows])
                    except Exception as e:
                        ui.notify(f'Errore salvataggio: {e}', type='warning')
                    if on_update:
                        try:
                            on_update()
                        except Exception:
                            pass

                def add():
                    name = (input_name.value or '').strip()
                    if not name or len(name) < 3:
                        ui.notify('Nome non valido.', type='warning'); return
                    if any(name.lower() == r['name'].lower() for r in rows):
                        ui.notify('Nome già presente.', type='warning'); return
                    rows.append({'name': name})
                    input_name.value = ''
                    aggiorna()

                def delete():
                    if not table.selected:
                        ui.notify('Seleziona una materia.', type='warning'); return
                    rows.remove(table.selected[0])
                    table.selected.clear()
                    input_name.value = ''
                    aggiorna()

                def modify():
                    if not table.selected:
                        ui.notify('Seleziona una materia.', type='warning'); return
                    new_name = (input_name.value or '').strip()
                    if not new_name or len(new_name) < 3:
                        ui.notify('Nome non valido.', type='warning'); return
                    selected = table.selected[0]['name']
                    if any(new_name.lower() == r['name'].lower() and r['name'] != selected for r in rows):
                        ui.notify('Nome già presente.', type='warning'); return
                    for r in rows:
                        if r['name'] == selected:
                            r['name'] = new_name
                            break
                    table.selected.clear()
                    input_name.value = ''
                    aggiorna()

                ui.button('Aggiungi', on_click=add)
                ui.button('Elimina', on_click=delete)
                ui.button('Modifica', on_click=modify)

        crea_pulsanti_controllo(dialog, card)

    dialog.open()


# --------- Settori ---------

def _load_settori() -> list[str]:
    if _load_settori_util:
        try:
            return sorted({s.strip() for s in _load_settori_util() if isinstance(s, str) and s.strip()})
        except Exception:
            pass
    return sorted({s.strip() for s in _read_list_from_json(SETTORI_JSON, 'settori')})


def _save_settori(items: list[str]) -> None:
    _save_list_to_json(SETTORI_JSON, 'settori', items)


def mostra_popup_modifica_settori(on_update=None):
    stile_popup()  # Applica stile globale

    rows = [{'name': i} for i in _load_settori()]

    dialog = ui.dialog().classes('w-full max-w-[95vw]')
    with dialog, ui.card().classes('popup-card min-w-[600px]') as card:
        ui.label('Gestione Settori').classes('popup-header')
        with ui.row():
            with ui.column().style('min-width: 300px'):
                table = ui.table(
                    columns=[{'name': 'name', 'label': 'Settore', 'field': 'name', 'sortable': True}],
                    rows=rows, row_key='name', selection='single'
                )
            with ui.column().style('min-width: 300px'):
                input_name = ui.input(label='Nome settore', placeholder='Inserisci nome...')

                def aggiorna():
                    table.update()
                    try:
                        _save_settori([r['name'] for r in rows])
                    except Exception as e:
                        ui.notify(f'Errore salvataggio: {e}', type='warning')
                    if on_update:
                        try:
                            on_update()
                        except Exception:
                            pass

                def add():
                    name = (input_name.value or '').strip()
                    if not name or len(name) < 3:
                        ui.notify('Nome non valido.', type='warning'); return
                    if any(name.lower() == r['name'].lower() for r in rows):
                        ui.notify('Nome già presente.', type='warning'); return
                    rows.append({'name': name})
                    input_name.value = ''
                    aggiorna()

                def delete():
                    if not table.selected:
                        ui.notify('Seleziona un settore.', type='warning'); return
                    rows.remove(table.selected[0])
                    table.selected.clear()
                    input_name.value = ''
                    aggiorna()

                def modify():
                    if not table.selected:
                        ui.notify('Seleziona un settore.', type='warning'); return
                    new_name = (input_name.value or '').strip()
                    if not new_name or len(new_name) < 3:
                        ui.notify('Nome non valido.', type='warning'); return
                    selected = table.selected[0]['name']
                    if any(new_name.lower() == r['name'].lower() and r['name'] != selected for r in rows):
                        ui.notify('Nome già presente.', type='warning'); return
                    for r in rows:
                        if r['name'] == selected:
                            r['name'] = new_name
                            break
                    table.selected.clear()
                    input_name.value = ''
                    aggiorna()

                ui.button('Aggiungi', on_click=add)
                ui.button('Elimina', on_click=delete)
                ui.button('Modifica', on_click=modify)

        crea_pulsanti_controllo(dialog, card)

    dialog.open()

