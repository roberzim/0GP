# avvocati_popup_def.py — versione JSON-only
from pathlib import Path
import json

from nicegui import ui
from utils import stile_popup, crea_pulsanti_controllo
from utils_lookup import load_avvocati  # lettura da lib_json/avvocati.json se disponibile

AVVOCATI_JSON = Path('lib_json/avvocati.json')


def _read_avvocati_from_file() -> list[str]:
    try:
        data = json.loads(AVVOCATI_JSON.read_text(encoding='utf-8'))
        if isinstance(data, dict):
            lst = data.get('avvocati', [])
        elif isinstance(data, list):
            lst = data
        else:
            lst = []
        return [s for s in lst if isinstance(s, str) and s.strip()]
    except Exception:
        return []


def load_lawyers() -> list[str]:
    """Ritorna l'elenco avvocati da utils_lookup / file JSON."""
    try:
        # Prova la funzione utilità (già usata in altre parti del progetto)
        lst = load_avvocati()
        return sorted({s.strip() for s in lst if isinstance(s, str) and s.strip()})
    except Exception:
        # Fallback: leggi direttamente dal file JSON
        return sorted({s.strip() for s in _read_avvocati_from_file()})


def save_lawyers(names: list[str]) -> None:
    """Salva su lib_json/avvocati.json usando lo schema {'avvocati': [...]}."""
    AVVOCATI_JSON.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        'avvocati': sorted({s.strip() for s in names if isinstance(s, str) and s.strip()})
    }
    AVVOCATI_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')


def mostra_popup_modifica_avvocati(on_update=None):
    stile_popup()  # Applica stile globale

    lawyer_names = load_lawyers()
    rows = [{'name': n} for n in lawyer_names]

    dialog = ui.dialog().classes('w-full')
    with dialog, ui.card().classes('popup-card') as card:
        ui.label('Gestione Avvocati').classes('popup-header')
        with ui.row():
            with ui.column().style('min-width: 300px'):
                columns = [{'name': 'name', 'label': 'Nome', 'field': 'name', 'sortable': True}]
                table = ui.table(columns=columns, rows=rows, row_key='name', selection='single')
            with ui.column().style('min-width: 300px'):
                input_name = ui.input(label='Nome avvocato', placeholder='Inserisci nome...')

                def aggiorna_tabelle():
                    table.update()
                    try:
                        save_lawyers([row['name'] for row in rows])
                    except Exception as e:
                        ui.notify(f'Errore salvataggio: {e}', type='warning')
                    if on_update:
                        try:
                            on_update()
                        except Exception:
                            pass

                def add():
                    name = (input_name.value or '').strip()
                    if name == '' or len(name) < 3:
                        ui.notify('Nome non valido.', type='warning')
                        return
                    if any(name.lower() == row['name'].lower() for row in rows):
                        ui.notify('Nome già presente.', type='warning')
                        return
                    rows.append({'name': name})
                    input_name.value = ''
                    aggiorna_tabelle()

                def delete():
                    if not table.selected:
                        ui.notify('Seleziona un avvocato.', type='warning')
                        return
                    rows.remove(table.selected[0])
                    table.selected.clear()
                    input_name.value = ''
                    aggiorna_tabelle()

                def modify():
                    if not table.selected:
                        ui.notify('Seleziona un avvocato.', type='warning')
                        return
                    new_name = (input_name.value or '').strip()
                    if new_name == '' or len(new_name) < 3:
                        ui.notify('Nome non valido.', type='warning')
                        return
                    selected = table.selected[0]['name']
                    if any(new_name.lower() == row['name'].lower() and row['name'] != selected for row in rows):
                        ui.notify('Nome già presente.', type='warning')
                        return
                    for i, row in enumerate(rows):
                        if row['name'] == selected:
                            rows[i]['name'] = new_name
                            break
                    table.selected.clear()
                    input_name.value = ''
                    aggiorna_tabelle()

                ui.button('Aggiungi', on_click=add)
                ui.button('Elimina', on_click=delete)
                ui.button('Modifica', on_click=modify)

        crea_pulsanti_controllo(dialog, card)

    dialog.open()

