# apertura_pratica_popup.py — versione JSON-only (NiceGUI “prime” + id_registry + gestione collisioni)
from __future__ import annotations

import os
import re
from datetime import datetime, date
from typing import Iterable, Tuple, Optional, Dict, Any
from pathlib import Path

from reindex import reindex
from nicegui import ui

from log_gestione_pratica import log_apertura

from repo import write_pratica
from utils_lookup import load_id_pratiche, load_avvocati
from id_registry import load_next_id, persist_after_save
from reindex import reindex


# Formato per la porzione data nel nome cartella cliente (es. _14082025)
DATA_FMT_CARTELLA = '%d%m%Y'


# ---------- Utility JSON-only ----------

def _load_avvocati_json() -> list[str]:
    """Avvocati da lib_json/avvocati.json (chiave: 'avvocati')."""
    try:
        lst = load_avvocati()
        return sorted({x for x in lst if isinstance(x, str) and x.strip()})
    except Exception:
        return []


def _make_id_suffix(numero: int, anno: int) -> str:
    """Concatena numero+anno con padding per ottenere 6 cifre (es. 1/2025 -> '012025')."""
    s = f'{numero}{anno}'
    return ('0' + s) if len(s) == 5 else s


def _read_ids_for_table() -> list[dict]:
    """Righe da mostrare nella tabella elenco pratiche (fonte: lib_json/id_pratiche.json via utils_lookup)."""
    rows = []
    try:
        for el in load_id_pratiche():  # ogni elemento è un dict
            rows.append({
                'Numero': el.get('num_pratica', ''),
                'Anno': el.get('anno_pratica', ''),
                'Nome pratica': el.get('nome_pratica', ''),
                'Cartella': el.get('percorso_pratica', '') or el.get('link_percorso_pratica', ''),
                'Link': el.get('link_cartella', ''),
            })
    except Exception:
        pass
    return rows


def _open_path(path: str) -> None:
    """Apre cartelle sul sistema dove gira il server NiceGUI."""
    try:
        if os.name == 'nt':
            os.startfile(path)  # type: ignore
        elif os.name == 'posix':
            if os.system(f'xdg-open "{path}" >/dev/null 2>&1') != 0:
                os.system(f'open "{path}" >/dev/null 2>&1')
        else:
            raise RuntimeError('Sistema non supportato')
    except Exception as e:
        ui.notify(f'Impossibile aprire: {e}', type='warning')


def _safe_int(x) -> int:
    try:
        return int(x)
    except Exception:
        return -10**9


# ---------- Supporto ID & Collisioni ----------

def _id_exists(numero: int, anno: int) -> Tuple[bool, Optional[str]]:
    """Ritorna (esiste, nome_pratica_esistente) per l'ID numero/anno."""
    try:
        for el in load_id_pratiche():
            try:
                n = int(str(el.get('num_pratica') or '0').strip())
                a = int(str(el.get('anno_pratica') or str(date.today().year)).strip())
            except Exception:
                continue
            if n == numero and a == anno:
                return True, str(el.get('nome_pratica') or '')
    except Exception:
        pass
    return False, None


def _next_id_for_year(anno: int) -> int:
    """Trova il primo numero disponibile per l'anno indicato (max(num_pratica)+1) o 1 se anno nuovo."""
    max_num = 0
    try:
        for el in load_id_pratiche():
            try:
                a = int(str(el.get('anno_pratica') or '0').strip())
                if a != anno:
                    continue
                n = int(str(el.get('num_pratica') or '0').strip())
                if n > max_num:
                    max_num = n
            except Exception:
                continue
    except Exception:
        pass
    return max_num + 1 if max_num >= 0 else 1


# ---------- Dialog secondari ----------

def _popup_elenco_pratiche() -> None:
    dlg = ui.dialog()
    with dlg, ui.card().classes('w-[800px] max-w-[95vw]'):
        ui.label('Elenco pratiche (da lib_json/id_pratiche.json)').classes('text-xl font-semibold')
        table_container = ui.column().classes('w-full')
        links_container = ui.column().classes('w-full mt-2')

        def render():
            table_container.clear()
            links_container.clear()

            rows = _read_ids_for_table()
            if not rows:
                with table_container:
                    ui.label('Nessun dato trovato.').classes('text-gray-500')
                return

            rows.sort(key=lambda r: (_safe_int(r.get('Anno')), _safe_int(r.get('Numero'))), reverse=True)
            cols = [{'name': k, 'label': k, 'field': k, 'align': 'left'} for k in rows[0].keys()]

            with table_container:
                ui.table(columns=cols, rows=rows).classes('w-full')

            with links_container:
                ui.separator()
                ui.label('Apri cartella').classes('text-sm text-gray-600')
                for r in rows:
                    cartella = r.get('Cartella') or ''
                    if cartella:
                        ui.button(
                            f"{r.get('Numero','')}/{r.get('Anno','')} — {r.get('Nome pratica','')}",
                            on_click=lambda p=cartella: _open_path(p)
                        ).props('flat color=primary')

        render()

        with ui.row().classes('justify-end w-full mt-3 gap-2'):
            ui.button('Aggiorna', on_click=render).props('icon=refresh')
            ui.button('Chiudi', on_click=dlg.close).props('icon=close')

    dlg.open()


def _file_browser_dialog(on_pick, start_dir: str | None = None) -> None:
    """Selettore di cartelle minimal server-side."""
    base = start_dir or os.path.expanduser('~')
    state = {'path': os.path.abspath(base)}

    dlg = ui.dialog().props('persistent')
    with dlg, ui.card().classes('w-[1000px] h-[70vh] max-w-[95vw]').style('resize: both; overflow: auto;'):
        ui.label('Seleziona cartella di destinazione').classes('text-xl font-semibold')
        with ui.row().classes('items-center justify-between w-full'):
            path_label = ui.input('Percorso corrente').props('readonly').classes('w-full mr-2')
            path_label.value = state['path']
            ui.button(
                'Seleziona questa cartella',
                on_click=lambda: (on_pick(state['path']), dlg.close())
            ).props('icon=check color=primary')

        ui.separator()
        lst_container = ui.column().classes('w-full h-full overflow-auto')

        def open_dir(path: str):
            try:
                path = os.path.abspath(path)
                if not os.path.isdir(path):
                    ui.notify('Percorso non valido', type='negative')
                    return
                state['path'] = path
                path_label.value = state['path']
                render_list()
            except Exception as e:
                ui.notify(f'Errore apertura cartella: {e}', type='negative')

        def render_list():
            lst_container.clear()
            with lst_container:
                with ui.row().classes('w-full justify-between items-center mb-2'):
                    ui.button('⬆️ Su', on_click=lambda: open_dir(os.path.dirname(state['path']))).props('flat')
                    ui.label(f'Contenuto di: {state["path"]}').classes('text-sm text-gray-600')
                try:
                    entries = sorted(os.listdir(state['path']))
                except Exception as e:
                    ui.notify(f'Errore lettura cartella: {e}', type='negative')
                    return
                for name in entries:
                    p = os.path.join(state['path'], name)
                    if os.path.isdir(p):
                        with ui.row().classes('w-full items-center justify-between hover:bg-gray-50 rounded px-2 py-1'):
                            ui.icon('folder').classes('mr-1')
                            ui.button(name, on_click=lambda p=p: open_dir(p)).props('flat')
                if not entries:
                    ui.label('Nessuna sottocartella').classes('text-gray-500')

        render_list()
    dlg.open()


# ---------- Dialog principale ----------

def mostra_popup_apertura(pratica_data: dict, id_predefinito: str, on_set_user_label, anagrafica_data: dict) -> None:
    # 0) usa il prossimo ID reale come default (evita mismatch con l’ID effettivo)
    try:
        num_default, anno_default = load_next_id()
    except Exception:
        oggi = date.today()
        num_default, anno_default = (1, oggi.year)

    id_suffix = _make_id_suffix(num_default, anno_default)
    oggi_str = datetime.now().strftime(DATA_FMT_CARTELLA)

    dialog = ui.dialog().props('persistent')
    with dialog, ui.card().classes('w-[1100px] h-[80vh] max-w-[95vw]').style('resize: both; overflow: auto;'):
        ui.label('Apertura nuova pratica').classes('text-3xl font-bold mb-2')

        # --- Header ID (informativo) ---
        with ui.row().classes('w-full gap-4 items-end'):
            ui.label('ID_pratica').classes('font-medium')
            # campi informativi: l’ID finale viene generato da load_next_id() al salvataggio
            in_num = ui.number('Numero', value=num_default, min=1, format='%d').classes('w-40').props('readonly')
            in_anno = ui.number('Anno', value=anno_default, min=2000, format='%d').classes('w-48').props('readonly')

        ui.separator()

        # --- Form principale ---
        with ui.grid(columns=2).classes('w-full gap-4'):
            avvocati = _load_avvocati_json()
            in_user = (
                ui.select(avvocati, label='Chi entra in gestione pratica *').classes('w-full')
                if avvocati else ui.input(label='Chi entra in gestione pratica *').classes('w-full')
            )
            in_cliente = ui.input(label='Nome cartella cliente *', value=f'_{oggi_str}').classes('w-full')
            in_pratica = ui.input(label='Nome pratica (sarà la cartella pratica) *', value=f'_{id_suffix}').classes('w-full')

            with ui.row().classes('items-end w-full gap-2'):
                in_percorso = ui.input(label='Percorso base dove creare le cartelle *').props('readonly').classes('w-full')
                ui.button('Sfoglia…', on_click=lambda: _file_browser_dialog(
                    lambda p: setattr(in_percorso, 'value', p), start_dir=os.getcwd()
                )).props('icon=folder_open color=primary')

        # --- Helper per suffissi e validazione ---
        pattern_cartella = re.compile(r'.*_\d{8}$')   # es. _DDMMAAAA
        pattern_cartella_p = re.compile(r'.*_\d{6}$') # es. _NNAAAA

        def _append_suffix_if_missing(inp, pattern: re.Pattern, suffix: str):
            v = (inp.value or '').strip()
            if not v or pattern.match(v):
                return
            base = v.rsplit('_', 1)[0] if '_' in v else v
            inp.value = f'{base}_{suffix}'
            try:
                inp.update()
            except Exception:
                pass

        def _validate_required() -> bool:
            fields: Iterable[tuple[str, object]] = [
                ('Nome utente', (in_user.value or '').strip() if hasattr(in_user, 'value') else ''),
                ('Nome cartella cliente', (in_cliente.value or '').strip()),
                ('Nome pratica', (in_pratica.value or '').strip()),
                ('Percorso base', (in_percorso.value or '').strip()),
            ]
            missing = [k for k, v in fields if (isinstance(v, str) and v.strip() == '') or v in (None, '')]
            if missing:
                ui.notify('Compila tutti i campi: ' + ', '.join(missing), type='warning')
                return False
            if not pattern_cartella.match((in_cliente.value or '').strip()):
                ui.notify('Il nome cartella cliente deve terminare con _######## (data, es. _14082025)', type='warning')
                return False
            if not pattern_cartella_p.match((in_pratica.value or '').strip()):
                ui.notify('Il nome pratica deve terminare con _###### (num+anno, es. _012025)', type='warning')
                return False
            return True

        # auto-completa i suffissi quando l’utente esce dal campo
        in_cliente.on('blur', lambda e: _append_suffix_if_missing(in_cliente, pattern_cartella, oggi_str))
        in_pratica.on('blur', lambda e: _append_suffix_if_missing(in_pratica, pattern_cartella_p, id_suffix))

        # --- Footer bottoni ---
        with ui.row().classes('w-full justify-between mt-2'):
            ui.button('Elenco pratiche', on_click=_popup_elenco_pratiche).props('icon=folder')

            with ui.row().classes('gap-2'):
                def hard_refresh():
                    ui.navigate.reload()

                def salva():
                    # 1) valida
                    if not _validate_required():
                        return

                    # 2) altri campi
                    user = (in_user.value or '').strip() if hasattr(in_user, 'value') else ''
                    cartella_cliente = (in_cliente.value or '').strip()
                    cartella_pratica = (in_pratica.value or '').strip()
                    base_path = (in_percorso.value or '').strip()

                    # 3) crea cartelle
                    cliente_path = os.path.join(base_path, cartella_cliente)
                    pratica_path = os.path.join(cliente_path, cartella_pratica)
                    try:
                        os.makedirs(os.path.join(pratica_path, 'log_pratica'), exist_ok=True)
                        os.makedirs(os.path.join(pratica_path, 'documenti_pratica'), exist_ok=True)
                    except Exception as e:
                        ui.notify(f'Errore creazione cartelle: {e}', type='negative')
                        return

                    # 4) genera primo ID proposto dal registro
                    numero, anno = load_next_id()
                    id_str = f"{numero}/{anno}"

                    # 5) collision check: stesso ID già esistente con nome diverso?
                    esiste, nome_esistente = _id_exists(numero, anno)
                    def _prosegui_salvataggio(def_num: int, def_anno: int):
                        id_eff = f"{def_num}/{def_anno}"
                        # aggiorna dati condivisi
                        pratica_data["id_pratica"] = id_eff
                        pratica_data['percorso_pratica'] = pratica_path
                        pratica_data['nome_pratica'] = cartella_pratica

                        # log non bloccante
                        try:
                            log_apertura(
                                user=user,
                                id_pratica=id_eff,
                                base_path=base_path,
                                cliente_path=cliente_path,
                                pratica_path=pratica_path,
                            )
                        except Exception as e:
                            ui.notify(f'Errore scrittura log: {e}', type='warning')

                        # salva + persist + reindex
                        try:
                             # Scrive il JSON “canonico” della pratica nella cartella della pratica
                             write_pratica(
                                 folder=Path(pratica_path),
                                 data=pratica_data,
                                 actor=user or "system",
                             )
                            persist_after_save(
                                def_num, def_anno,
                                pratica_data.get("nome_pratica",""),
                                pratica_data.get("percorso_pratica",""),
                                created_by=user
                            )
                            # reindicizza subito
                            reindex(root=Path("archivio"), db_path=Path("archivio/indice.sqlite"))
                        except Exception as e:
                            ui.notify(f"Reindex fallito: {e}", type="warning")
                            return

                        try:
                            on_set_user_label(user)
                        except Exception:
                            pass

                        ui.notify(f'Pratica {id_eff} creata e salvata correttamente', type='positive')
                        dialog.close()

                    if esiste and (nome_esistente or '') != cartella_pratica:
                        # Dialog di scelta: sovrascrivi o usa prossimo ID
                        d = ui.dialog()
                        with d, ui.card().classes('w-[700px] max-w-[95vw]'):
                            ui.label('Conflitto ID pratica').classes('text-xl font-semibold')
                            ui.separator()
                            ui.label(
                                f"L'ID {id_str} esiste già"
                                + (f" con nome: {nome_esistente!r}." if nome_esistente else ".")
                                + " Vuoi sovrascrivere questo ID o usare il primo ID successivo disponibile?"
                            ).classes('text-sm')
                            ui.separator()
                            with ui.row().classes('justify-end gap-2 w-full'):
                                def _sovrascrivi():
                                    d.close()
                                    _prosegui_salvataggio(numero, anno)
                                def _usa_prossimo():
                                    d.close()
                                    nuovo_num = _next_id_for_year(anno)
                                    _prosegui_salvataggio(nuovo_num, anno)
                                ui.button('Sovrascrivi (stesso ID)', on_click=_sovrascrivi).props('color=negative')
                                ui.button('Usa prossimo ID', on_click=_usa_prossimo).props('color=primary')
                                ui.button('Annulla', on_click=d.close).props('flat')
                        d.open()
                        return
                    else:
                        # Nessuna collisione, procedi con l'ID proposto
                        _prosegui_salvataggio(numero, anno)

                ui.button('SALVA', on_click=salva).props('icon=save color=positive')
                ui.button('', on_click=hard_refresh).props('icon=refresh flat')

    dialog.open()
