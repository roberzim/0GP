"""
Modulo: pratica.py
Contiene la funzione per costruire la scheda 'Pratica' nell'interfaccia utente.
"""
from __future__ import annotations

import os
from typing import List
from nicegui import ui
from utils_lookup import load_tariffe, load_tipo_pratica, load_settori, load_materie, load_avvocati


def _open_path(path: str) -> None:
    try:
        if os.name == 'nt':
            os.startfile(path)  # type: ignore
        elif os.name == 'posix':
            # prova xdg-open, altrimenti 'open' (macOS)
            if os.system(f'xdg-open "{path}" >/dev/null 2>&1') != 0:
                os.system(f'open "{path}" >/dev/null 2>&1')
        else:
            raise RuntimeError('Sistema non supportato')
    except Exception as e:
        ui.notify(f'Impossibile aprire: {e}', type='warning')


def _safe(fn, default):
    try:
        return fn()
    except Exception as e:
        ui.notify(f"Errore: {e}", type='negative')
        return default


def costruisci_tab_pratica(id_pratica: str) -> dict:
    """
    Costruisce la UI per la scheda 'Pratica' e restituisce un dizionario con i dati della pratica.
    """
    # lookups (JSON)
    TARIFFE: List[str] = _safe(load_tariffe, [])
    TIPI: List[str] = _safe(load_tipo_pratica, [])
    SETTORI: List[str] = _safe(load_settori, [])
    MATERIE: List[str] = _safe(load_materie, [])
    AVVOCATI: List[str] = _safe(load_avvocati, [])

    # stato condiviso dalla scheda
    pratica_data: dict = {
        # chiavi allineate allo schema JSON del progetto
        'id_pratica': id_pratica,
        'nome_pratica': '',
        'percorso_pratica': '',
        'data_apertura': None,
        'data_chiusura': None,
        'valore_pratica': '',
        'tipo_pratica': None,
        'settore_pratica': None,
        'materia_pratica': None,
        'avvocato_referente': None,
        'avvocato_in_mandato': [],         # <- lista di stringhe
        'preventivo_inviato': False,       # <- boolean
        'note': '',
        'tipo_tariffe': [],                # <- lista di stringhe, NON widget
    }

    # contenitore per gestire i widget select delle tariffe (solo per UI)
    pratica_data['_tariffe_widgets'] = []

    with ui.row().classes('w-full no-wrap gap-4'):
        # Colonna sinistra - Informazioni base
        with ui.column().classes('w-1/2 gap-4'):
            with ui.card().classes('w-full p-4 shadow-md'):
                ui.label('Informazioni Base').classes('text-lg font-bold mb-2')

                with ui.row().classes('items-center gap-4 mb-4'):
                    ui.label().bind_text_from(
                        pratica_data, 'id_pratica', lambda v: f'ID pratica: {v}'
                    ).classes('text-sm text-gray-600')
                    ui.label().bind_text_from(
                        pratica_data, 'nome_pratica', lambda v: f'Nome pratica: {v or "-"}'
                    ).classes('text-sm text-gray-600')

                # Percorso pratica (readonly) + link aggiornabile
                ui.input(label='Percorso pratica', value=pratica_data['percorso_pratica']) \
                    .props('readonly').classes('w-full mb-1') \
                    .bind_value(pratica_data, 'percorso_pratica')

                ui.button(
                    'Apri cartella',
                    icon='folder_open',
                    on_click=lambda: _open_path(pratica_data.get('percorso_pratica', '') or '')
                ).props('color=primary flat')

                ui.label('Data apertura *').classes('font-medium')
                ui.date().classes('w-full mb-2').on(
                    'update:model-value',
                    lambda e: pratica_data.update({'data_apertura': e.args})
                ).tooltip('Campo obbligatorio')

                ui.label('Data chiusura').classes('font-medium')
                ui.date().classes('w-full').on(
                    'update:model-value',
                    lambda e: pratica_data.update({'data_chiusura': e.args})
                )

        # Colonna destra - Dettagli pratica
        with ui.column().classes('w-1/2 gap-4'):
            with ui.card().classes('w-full p-4 shadow-md'):
                ui.label('Dettagli Pratica').classes('text-lg font-bold mb-2')

                ui.input(label='Valore pratica *').classes('w-full mb-2') \
                    .on('update:model-value', lambda e: pratica_data.update({'valore_pratica': e.args})) \
                    .tooltip('Campo obbligatorio')

                ui.select(TIPI, label='Tipo pratica *').classes('w-full mb-2') \
                    .on('update:model-value', lambda e: pratica_data.update({'tipo_pratica': e.args})) \
                    .tooltip('Campo obbligatorio')

                # select con refresher live
                pratica_data['settore_element'] = ui.select(SETTORI, label='Settore pratica') \
                    .classes('w-full mb-2') \
                    .on('update:model-value', lambda e: pratica_data.update({'settore_pratica': e.args}))

                pratica_data['materia_element'] = ui.select(MATERIE, label='Materia della pratica') \
                    .classes('w-full mb-2') \
                    .on('update:model-value', lambda e: pratica_data.update({'materia_pratica': e.args}))

                # --- REFRESHERS per aggiornare in tempo reale le select ---
                def refresh_settori():
                    try:
                        nuovi = load_settori()
                        sel = pratica_data['settore_element']
                        cur = getattr(sel, 'value', None)
                        sel.options = nuovi
                        if cur in nuovi:
                            sel.value = cur
                        sel.update()
                    except Exception as e:
                        ui.notify(f'Errore refresh settori: {e}', type="negative")

                def refresh_materie():
                    try:
                        nuove = load_materie()
                        sel = pratica_data['materia_element']
                        cur = getattr(sel, 'value', None)
                        sel.options = nuove
                        if cur in nuove:
                            sel.value = cur
                        sel.update()
                    except Exception as e:
                        ui.notify(f'Errore refresh materie: {e}', type="negative")

                def refresh_avvocati():
                    try:
                        nuovi = load_avvocati()
                        sel_ref = pratica_data['avv_referente_element']
                        sel_mand = pratica_data['avv_mandato_element']
                        cur_ref = getattr(sel_ref, 'value', None)
                        cur_mand = (getattr(sel_mand, 'value', None) or [])
                        sel_ref.options = nuovi
                        if cur_ref in nuovi:
                            sel_ref.value = cur_ref
                        sel_ref.update()
                        sel_mand.options = nuovi
                        sel_mand.value = [v for v in cur_mand if v in nuovi]
                        sel_mand.update()
                    except Exception as e:
                        ui.notify(f'Errore refresh avvocati: {e}', type='negative')

            with ui.card().classes('w-full p-4 shadow-md'):
                ui.label('Avvocati').classes('text-lg font-bold mb-2')

                pratica_data['avv_referente_element'] = ui.select(
                    AVVOCATI,
                    label='Avvocato referente *'
                ).classes('w-full mb-2') \
                 .on('update:model-value', lambda e: pratica_data.update({'avvocato_referente': e.args})) \
                 .tooltip('Campo obbligatorio')

                pratica_data['avv_mandato_element'] = ui.select(
                    AVVOCATI,
                    label='Avvocati in mandato',
                    multiple=True
                ).classes('w-full mb-2') \
                 .on('update:model-value', lambda e: pratica_data.update({'avvocato_in_mandato': e.args or []}))

            with ui.card().classes('w-full p-4 shadow-md'):
                ui.label('Altre Informazioni').classes('text-lg font-bold mb-2')

                ui.checkbox('Preventivo inviato') \
                    .on('update:model-value', lambda e: pratica_data.update({'preventivo_inviato': bool(e.args)})) \
                    .classes('mb-2')

                ui.textarea(label='Note') \
                    .on('update:model-value', lambda e: pratica_data.update({'note': e.args})) \
                    .classes('w-full mb-2')

            with ui.card().classes('w-full p-4 shadow-md'):
                ui.label('Tariffe').classes('text-lg font-bold mb-2')

                tipo_tariffa_container = ui.column().classes('w-full gap-2 mb-2')

                def _make_tariffa_row(idx: int, value: str | None = None):
                    # crea una riga con select + bottone elimina
                    row = ui.row().classes('items-end gap-2 w-full')
                    with row:
                        sel = ui.select(TARIFFE, label=f'Tipo di tariffa #{idx + 1}', value=value) \
                            .classes('w-full')
                        # aggiorna la lista stringhe
                        sel.on('update:model-value', lambda e, i=idx: _set_tariffa(i, e.args))
                        ui.button('', icon='delete', on_click=lambda i=idx: _remove_tariffa(i)) \
                            .props('color=negative flat')

                    # memorizza widget e contenitore
                    pratica_data['_tariffe_widgets'].append((row, sel))

                def _set_tariffa(i: int, v: str | None):
                    # estendi lista se necessario
                    while len(pratica_data['tipo_tariffe']) <= i:
                        pratica_data['tipo_tariffe'].append(None)
                    pratica_data['tipo_tariffe'][i] = v

                def _reindex_tariffe_widgets():
                    # rinomina le label in base al nuovo indice
                    for i, (row, sel) in enumerate(pratica_data['_tariffe_widgets']):
                        try:
                            sel.label = f'Tipo di tariffa #{i + 1}'
                            sel.update()
                        except Exception:
                            pass

                def _remove_tariffa(i: int):
                    # rimuovi i-esima riga
                    if 0 <= i < len(pratica_data['_tariffe_widgets']):
                        row, sel = pratica_data['_tariffe_widgets'].pop(i)
                        try:
                            row.delete()
                        except Exception:
                            pass
                    if 0 <= i < len(pratica_data['tipo_tariffe']):
                        pratica_data['tipo_tariffe'].pop(i)
                    _reindex_tariffe_widgets()

                def aggiungi_tariffa():
                    idx = len(pratica_data['_tariffe_widgets'])
                    _make_tariffa_row(idx)

                with tipo_tariffa_container:
                    # inizialmente vuoto; l'utente può aggiungere righe
                    pass

                with ui.row().classes('w-full justify-end gap-2'):
                    ui.button('Aggiungi tariffa', on_click=aggiungi_tariffa) \
                        .props('icon=add color=positive')
                    ui.button('Elimina tutte', on_click=lambda: (
                        [row.delete() for row, _ in pratica_data['_tariffe_widgets']],
                        pratica_data['_tariffe_widgets'].clear(),
                        pratica_data['tipo_tariffe'].clear()
                    )).props('icon=delete color=negative')

        # Rendi richiamabili dall’esterno (per popup che aggiornano i JSON)
        pratica_data['refresh_settori'] = refresh_settori
        pratica_data['refresh_materie'] = refresh_materie
        pratica_data['refresh_avvocati'] = refresh_avvocati

    return pratica_data
