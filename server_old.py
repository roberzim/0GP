from __future__ import annotations

from nicegui import ui, app
from datetime import date, datetime
from pathlib import Path
import os, json
from typing import Any, Dict
from collections.abc import Mapping
from nicegui.element import Element as _NgElement

# app modules
from salva_tutto import salva_pratica
from apertura_pratica_popup import mostra_popup_apertura, _popup_elenco_pratiche
from pratica import costruisci_tab_pratica
from anagrafica import gestisci_tab_anagrafica
from preventivi_tariffe import gestisci_tab_preventivi
from scadenza_attivita import mostra_tab_attivita
from documentazione import costruisci_tab_documentazione
from materia_settore_popup_def import mostra_popup_modifica_materie, mostra_popup_modifica_settori
from avvocati_popup_def import mostra_popup_modifica_avvocati
from calcola_ore_popup_def import mostra_popup_calcola_ore

# ---------------------------------------------------------------------
# Utility per serializzazione sicura (evita 'Select is not JSON serializable')
# ---------------------------------------------------------------------
def to_jsonable(x):
    if x is None or isinstance(x, (str, int, float, bool)):
        return x
    if isinstance(x, (date, datetime)):
        return x.isoformat()
    if isinstance(x, Path):
        return str(x)
    if isinstance(x, Mapping):
        out = {}
        for k, v in x.items():
            ks = str(k)
            if ks.startswith('refresh_') or ks.startswith('_ui_'):
                continue
            out[ks] = to_jsonable(v)
        return out
    if isinstance(x, (list, tuple, set)):
        return [to_jsonable(v) for v in x]
    # Elementi NiceGUI: prova .value se presente
    if isinstance(x, _NgElement):
        return to_jsonable(getattr(x, 'value', None))
    if hasattr(x, 'value'):
        try:
            return to_jsonable(getattr(x, 'value'))
        except Exception:
            return None
    if callable(x):
        return None
    return None

# --- Monkey patch globale per json.dump(s) ---
import json as _json
_orig_dump = _json.dump
_orig_dumps = _json.dumps
def _safe_dump(obj, fp, *args, **kwargs):
    kwargs.setdefault('default', to_jsonable)
    return _orig_dump(obj, fp, *args, **kwargs)
def _safe_dumps(obj, *args, **kwargs):
    kwargs.setdefault('default', to_jsonable)
    return _orig_dumps(obj, *args, **kwargs)
_json.dump = _safe_dump
_json.dumps = _safe_dumps

# ---------------------------------------------------------------------
# Dirty-flag & badge UI
# ---------------------------------------------------------------------
_is_dirty = {'value': False}
_dirty_badge_ref = {'badge': None}

def _update_dirty_badge():
    badge = _dirty_badge_ref.get('badge')
    if not badge:
        return
    if _is_dirty['value']:
        badge.text = 'MODIFICHE NON SALVATE'
        badge.props('color=warning')
        badge.visible = True
    else:
        badge.text = 'Tutto salvato'
        badge.props('color=positive')
        badge.visible = True

def mark_dirty(*args, **kwargs):
    _is_dirty['value'] = True
    _update_dirty_badge()

def clear_dirty():
    _is_dirty['value'] = False
    _update_dirty_badge()

# ---------------------------------------------------------------------
# Gestione ID pratica persistente
# ---------------------------------------------------------------------
ID_STATE_FILE = Path('lib_json/id_pratica.json')

def _load_id_state() -> Dict[str, Any]:
    if ID_STATE_FILE.exists():
        try:
            return json.loads(ID_STATE_FILE.read_text(encoding='utf-8')) or {}
        except Exception:
            return {}
    return {}

def _save_id_state(ultimo_numero: int, anno: int) -> None:
    ID_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {'ultimo_numero': int(ultimo_numero), 'anno': int(anno)}
    ID_STATE_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')

def leggi_id_pratica() -> tuple[int, int]:
    data = _load_id_state()
    anno_corr = date.today().year
    num = int(data.get('ultimo_numero') or 0)
    anno = int(data.get('anno') or anno_corr)
    return num, anno

# Calcolo nuovo ID pratica proposto
numero_corrente, anno_mem = leggi_id_pratica()
anno_corrente = date.today().year
numero_proposto = (numero_corrente + 1) if (anno_mem == anno_corrente) else 1
anno_proposto = anno_corrente
id_pratica = f"{numero_proposto}/{anno_proposto}"

# Inizializza struttura anagrafica
anagrafica_data: Dict[str, Any] = {'fisiche': [], 'giuridiche': []}

# ---------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------
with ui.row().classes('w-full bg-gray-50'):
    ui.add_head_html('''
    <style>
        :root {
            --primary-color: #2563eb;
            --secondary-color: #1e40af;
            --danger-color: #dc2626;
            --success-color: #16a34a;
            --card-shadow: 0 4px 2px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
        }
        .nicegui-button { transition: all 0.2s ease; }
        .nicegui-button:hover { transform: translateY(-1px); }
    </style>
    ''')

with ui.row().classes('w-full h-screen bg-gray-50'):
    # Colonna principale
    with ui.column().classes('w-3/4 p-4 h-full overflow-auto'):

        with ui.row().classes('w-full items-center justify-between'):
            ui.label('Gestione Pratica Legale - Apertura pratica').classes('text-2xl font-bold text-gray-800 mb-0')

            user_label = ui.label('').classes('text-sm text-gray-700 mt-0')

            with ui.column().classes('items-end gap-1'):
                ui.label(datetime.now().strftime('%d/%m/%Y')).classes('text-sm text-gray-600')
                ora_label = ui.label().classes('text-sm text-gray-600')
                def aggiorna_ora():
                    ora_label.text = datetime.now().strftime('%H:%M:%S')
                ui.timer(1.0, aggiorna_ora)

                _dirty_badge_ref['badge'] = ui.badge('Tutto salvato').classes('mt-1')
                _update_dirty_badge()

                ui.button(icon='refresh', on_click=lambda: ui.navigate.reload()).props('flat color=primary').classes('mt-1')

        with ui.tabs().props('dense active-color="var(--primary-color)"').classes('w-full bg-white rounded-lg shadow-sm mb-4') as tabs:
            tab_pratica = ui.tab('Pratica', icon='description')
            tab_anagrafica = ui.tab('Anagrafica', icon='people')
            tab_preventivi = ui.tab('Preventivi', icon='euro_symbol')
            tab_attivita = ui.tab('Scadenze ed attività', icon='event')
            tab_documentazione = ui.tab('Documentazione', icon='folder')

        with ui.tab_panels(tabs, value=tab_pratica).classes('w-full bg-white rounded-lg shadow-sm p-4'):

            with ui.tab_panel(tab_pratica):
                pratica_data = costruisci_tab_pratica(id_pratica)
                pratica_data['id_pratica'] = id_pratica

                # --- Merge eventuale pratica caricata da popup ---
                try:
                    from nicegui import app as _app_
                    _loaded = _app_.storage.general.get('pratica_loaded_record')
                    if _loaded and isinstance(_loaded, dict):
                        # Aggiorna pratica_data e anagrafica
                        for k, v in _loaded.items():
                            if k == 'anagrafica' and isinstance(v, dict):
                                fis = v.get('persone_fisiche') or v.get('fisiche') or []
                                giu = v.get('persone_giuridiche') or v.get('giuridiche') or []
                                if isinstance(fis, list): anagrafica_data['fisiche'] = fis
                                if isinstance(giu, list): anagrafica_data['giuridiche'] = giu
                            else:
                                pratica_data[k] = v
                        _app_.storage.general['pratica_loaded_record'] = None
                except Exception as _e_merge:
                    print('[WARN] merge pratica_loaded_record fallito:', _e_merge)

                # set utente dal popup apertura
                def _set_user(name: str):
                    user_label.text = f'Utente: {name}'

                # Apri il popup subito dopo il render
                ui.timer(0.1, lambda: mostra_popup_apertura(pratica_data, id_pratica, _set_user, anagrafica_data), once=True)

            with ui.tab_panel(tab_anagrafica):
                _res = gestisci_tab_anagrafica(anagrafica_data, on_change=mark_dirty)
                if isinstance(_res, dict):
                    anagrafica_data = _res

            with ui.tab_panel(tab_preventivi):
                gestisci_tab_preventivi(pratica_data=pratica_data, on_change=mark_dirty)

            with ui.tab_panel(tab_attivita):
                mostra_tab_attivita(pratica_data=pratica_data, on_change=mark_dirty)

            with ui.tab_panel(tab_documentazione):
                costruisci_tab_documentazione(pratica_data)

    # Colonna laterale (azioni)
    with ui.column().classes('w-4/4 p-4 bg-white border-l border-gray-200 h-full'):
        ui.label('Azioni').classes('text-xl font-bold text-gray-800 mb-4')

        with ui.card().classes('w-full mb-4 shadow-md'):
            ui.label('Gestione Pratica').classes('font-semibold mb-2 text-gray-700')

            def _salva_wrapper():
                # Serializza in modo sicuro e delega a salva_pratica
                pratica_clean = to_jsonable(pratica_data)
                anagrafica_clean = to_jsonable(anagrafica_data)

                try:
                    json.dumps(pratica_clean)  # sanity check
                    json.dumps(anagrafica_clean)
                except TypeError as e:
                    ui.notify(f'Serializzazione JSON fallita: {e}', color='negative')
                    return

                out = salva_pratica(pratica_clean, anagrafica_clean)
                if out:
                    clear_dirty()
                    try:
                        _save_id_state(numero_proposto, anno_proposto)
                    except Exception:
                        pass

            ui.button('SALVA PRATICA', icon='save', color='positive').classes('w-full mb-2 bg-green-600 hover:bg-green-700 text-white').on('click', _salva_wrapper)

            # RIMOSSO: 'Modifica pratica' dalla scheda, come richiesto
            ui.button('Elenco pratiche', icon='folder').classes('w-full mb-2 hover:bg-blue-50').on('click', _popup_elenco_pratiche)

        with ui.card().classes('w-full mb-4 shadow-md'):
            ui.label('Configurazioni').classes('font-semibold mb-2 text-gray-700')
            ui.button('Modifica settori', icon='category').classes('w-full mb-2 hover:bg-blue-50').on('click', lambda: mostra_popup_modifica_settori(
                    on_update=lambda: pratica_data.get('refresh_settori', lambda: None)()
                ))

            ui.button('Modifica materie', icon='book').classes('w-full mb-2 hover:bg-blue-50').on('click', lambda: mostra_popup_modifica_materie(
                    on_update=lambda: pratica_data.get('refresh_materie', lambda: None)()
                ))

            ui.button('Modifica avvocati', icon='people').classes('w-full mb-2 hover:bg-blue-50').on('click', lambda: mostra_popup_modifica_avvocati(
                    on_update=lambda: pratica_data.get('refresh_avvocati', lambda: None)()
                ))

        with ui.card().classes('w-full shadow-md'):
            ui.label('Strumenti').classes('font-semibold mb-2 text-gray-700')
            ui.button('Calcola Tariffa', icon='calculate').classes('w-full mb-2 hover:bg-blue-50').on('click', lambda: ui.navigate.to('/static/calcola_tariffa_def.html', new_tab=True))
            ui.button('Scadenze', icon='event_note').classes('w-full mb-2 hover:bg-blue-50')
            ui.button('Calcola Ore', icon='schedule').classes('w-full mb-2 hover:bg-blue-50').on('click', lambda: mostra_popup_calcola_ore())
            ui.button('Calendario', icon='calendar_today').classes('w-full mb-2 hover:bg-blue-50')
            ui.button('Report', icon='assessment').classes('w-full hover:bg-blue-50')

# Static
app.add_static_files('/static', os.path.join(os.path.dirname(__file__), 'static'))

# --- LOG DI SISTEMA (console + file) ---
try:
    from pathlib import Path as _Path
    import sys, traceback

    orig_stdout = sys.__stdout__
    orig_stderr = sys.__stderr__

    _log_dir = _Path('logs') / 'log_gestione_pratica'
    _log_dir.mkdir(parents=True, exist_ok=True)
    _log_file = _log_dir / 'log_sistema.txt'

    class _Tee:
        def __init__(self, *files):
            self.files = files
        def write(self, obj):
            for f in self.files:
                try:
                    f.write(obj); f.flush()
                except Exception:
                    pass
        def flush(self):
            for f in self.files:
                try: f.flush()
                except Exception: pass
        def isatty(self):
            return any(getattr(f, 'isatty', lambda: False)() for f in self.files)

    sys.stdout = _Tee(orig_stdout, open(_log_file, 'a', encoding='utf-8'))
    sys.stderr = _Tee(orig_stderr, open(_log_file, 'a', encoding='utf-8'))

    def _excepthook(exc_type, exc_value, exc_tb):
        # Silenzia i normali shutdown (CancelledError/KeyboardInterrupt) nei log
        try:
            import asyncio
            if exc_type in (KeyboardInterrupt, asyncio.CancelledError):
                return
        except Exception:
            pass
        with open(_log_file, 'a', encoding='utf-8') as f:
            f.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] UNCAUGHT EXCEPTION\n")
            traceback.print_exception(exc_type, exc_value, exc_tb, file=f)
    sys.excepthook = _excepthook
except Exception:
    pass

ui.run(title='Studio Legale Associato - Gestione Pratiche', favicon='⚖️', reload=False)
