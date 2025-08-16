from __future__ import annotations

from typing import Any, Dict, Optional
from pathlib import Path
import json
import os

from nicegui import ui


def _txt(v: Any) -> str:
    return '' if v is None else str(v).strip()


def _try_update_widget(widget, value):
    try:
        if widget is None:
            return
        # Set value if property exists, then update UI
        if hasattr(widget, 'value'):
            widget.value = value
        if hasattr(widget, 'update'):
            widget.update()
    except Exception:
        pass


def apply_record_to_state(record: Dict[str, Any], pratica_data: Dict[str, Any], anagrafica_data: Dict[str, Any]) -> None:
    """Copia i valori dal JSON 'record' nei dizionari di stato già usati dalla UI.
    Non inserisce oggetti UI nel modello; aggiorna i widget se presenti in pratica_data.
    """
    if not isinstance(record, dict):
        return

    # Campi base pratica
    mapping = [
        'id_pratica',
        'percorso_pratica',
        'data_apertura',
        'data_chiusura',
        'valore_pratica',
        'tipo_pratica',
        'settore_pratica',
        'materia_pratica',
        'note',
    ]
    for k in mapping:
        if k in record:
            pratica_data[k] = record.get(k)

    # Avvocati / flag
    pratica_data['avvocato_referente'] = record.get('avvocato_referente') or pratica_data.get('avvocato_referente')
    pratica_data['avvocato_in_mandato'] = record.get('avvocato_in_mandato') or pratica_data.get('avvocato_in_mandato') or []
    pratica_data['preventivo_inviato'] = bool(record.get('preventivo_inviato', pratica_data.get('preventivo_inviato', False)))

    # Tariffe e tabelle (se presenti nel record)
    for key in ('tariffe_contenzioso', 'tariffe_stragiudiziale', 'preventivi', 'preventivi_stragiudiziale', 'scadenze'):
        if key in record:
            pratica_data[key] = record.get(key)

    # Tipo tariffe (lista di stringhe)
    if 'tipo_tariffe' in record and isinstance(record['tipo_tariffe'], list):
        pratica_data['tipo_tariffe'] = [str(x) for x in record['tipo_tariffe'] if str(x).strip()]

    # Anagrafica (se presente)
    ana = record.get('anagrafica') or {}
    if isinstance(ana, dict):
        fis = ana.get('persone_fisiche') or []
        giu = ana.get('persone_giuridiche') or []
        if isinstance(fis, list):
            anagrafica_data['fisiche'] = fis
        if isinstance(giu, list):
            anagrafica_data['giuridiche'] = giu

    # Aggiorna i widget se esistono riferimenti nella pratica
    _try_update_widget(pratica_data.get('settore_element'), pratica_data.get('settore_pratica'))
    _try_update_widget(pratica_data.get('materia_element'), pratica_data.get('materia_pratica'))
    _try_update_widget(pratica_data.get('avv_referente_element'), pratica_data.get('avvocato_referente'))
    _try_update_widget(pratica_data.get('avv_mandato_element'), pratica_data.get('avvocato_in_mandato'))


def _safe_read_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        text = Path(path).read_text(encoding='utf-8')
        return json.loads(text)
    except Exception as e:
        ui.notify(f'JSON non valido: {e}', color='negative')
        return None


def _open_folder(path: str) -> None:
    try:
        if not path:
            return
        if os.name == 'nt':
            os.startfile(path)  # type: ignore
        elif os.name == 'posix':
            if os.system(f'xdg-open "{path}" >/dev/null 2>&1') != 0:
                os.system(f'open "{path}" >/dev/null 2>&1')
    except Exception as e:
        ui.notify(f'Impossibile aprire cartella: {e}', color='warning')


def costruisci_area_modifica(pratica_data: Dict[str, Any], anagrafica_data: Dict[str, Any], on_change=None) -> None:
    """Crea l'area UI per il CARICAMENTO e la MODIFICA di una pratica esistente (da file JSON).
    - Colonna destra del tab_pratica
    - Supporta upload diretto del JSON o selezione manuale di un percorso sul server
    - Dopo il caricamento, popola lo stato e richiama on_change()
    """
    with ui.card().classes('w-full p-4 shadow-md'):
        ui.label('Modifica pratica esistente').classes('text-lg font-bold mb-3')
        ui.label('Carica un file JSON già salvato nella cartella della pratica.').classes('text-sm text-gray-600 mb-2')

        # --- Upload tramite componente NiceGUI ---
        status = ui.label('').classes('text-xs text-gray-600 mb-2')

        def handle_upload(e):
            try:
                # Supporta diversi tipi di payload a seconda della versione di NiceGUI
                payload = getattr(e, 'content', None)
                if payload is None:
                    payload = getattr(e, 'file', None)
                if payload is None:
                    ui.notify('Upload vuoto', color='negative')
                    return

                # bytes -> decode; file-like -> read
                if hasattr(payload, 'read'):
                    data = payload.read()
                else:
                    data = payload

                if isinstance(data, bytes):
                    text = data.decode('utf-8')
                else:
                    text = str(data)

                record = json.loads(text)
            except Exception as exc:
                ui.notify(f'Caricamento fallito: {exc}', color='negative')
                return

            apply_record_to_state(record, pratica_data, anagrafica_data)
            status.text = 'File caricato correttamente'
            ui.notify('Dati caricati nella pratica', color='positive')
            if callable(on_change):
                on_change()

        ui.upload(label='Seleziona file JSON', on_upload=handle_upload).props('accept=.json').classes('mb-2')

        # --- Caricamento da percorso file (server-side) ---
        path_state: Dict[str, Any] = {'path': ''}
        ui.input('Oppure percorso file JSON sul server', placeholder='/percorso/pratica/9_2025_gp_11082025_170314.json').bind_value(path_state, 'path').classes('w-full mb-2')

        def load_from_path():
            p = Path(_txt(path_state.get('path')))
            if not p.exists():
                ui.notify('Percorso non trovato', color='negative'); return
            record = _safe_read_json(p)
            if not record:
                return
            apply_record_to_state(record, pratica_data, anagrafica_data)
            ui.notify('Dati caricati dalla path', color='positive')
            if callable(on_change):
                on_change()

        with ui.row().classes('gap-2 mb-2'):
            ui.button('Carica da percorso', on_click=load_from_path).props('icon=folder_open color=primary flat')
            ui.button('Apri cartella pratica', on_click=lambda: _open_folder(pratica_data.get('percorso_pratica', ''))).props('icon=folder flat')

        # --- Riepilogo rapido ---
        with ui.column().classes('gap-1 mt-2'):
            ui.label().bind_text_from(pratica_data, 'id_pratica', lambda v: f'ID pratica: {v or "(n/d)"}').classes('text-sm')
            ui.label().bind_text_from(pratica_data, 'percorso_pratica', lambda v: f'Cartella: {v or "(non impostata)"}').classes('text-sm')
