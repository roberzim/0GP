# persone_giuridiche_popup_def.py — JSON-only (rubrica + posizioni da lib_json)
from __future__ import annotations

from nicegui import ui
from pathlib import Path
import json, os
from typing import List, Dict, Optional, Callable

from posizioni_popup_def import mostra_popup_posizioni
from utils_lookup import load_posizioni

PG_JSON = Path("lib_json/persone_giuridiche.json")


# --------------------- IO JSON (con scrittura atomica) ---------------------

def _carica_persone() -> List[Dict[str, str]]:
    if PG_JSON.exists():
        try:
            data = json.loads(PG_JSON.read_text(encoding="utf-8"))
            lista = data.get("persone_giuridiche") or []
            return [r for r in lista if isinstance(r, dict)]
        except Exception:
            return []
    return []

def _salva_persone(lista: List[Dict[str, str]]) -> None:
    PG_JSON.parent.mkdir(parents=True, exist_ok=True)
    payload = {"persone_giuridiche": lista}
    tmp = PG_JSON.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, PG_JSON)  # atomico su stessa partizione


# --------------------- Utils dati / validazione ---------------------

BASE_COLS = [
    'Posizione',
    'Denominazione', 'Cod_fisc', 'P_IVA',
    'Indirizzo_legale', 'Altro_indirizzo',
    'PEC', 'Email', 'Num_telefoni',
    'Iscrizione_camerale',
    'Nome_rappresentante', 'Cognome_rappresentante', 'CodFisc_rappresentante',
    'Note'
]

def _strip_dict(d: Dict[str, str]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for k in d.keys() | set(BASE_COLS):
        v = d.get(k, "")
        out[k] = (v.strip() if isinstance(v, str) else v) or ""
    return out

def _norm_cf(cf: str) -> str:
    return (cf or "").replace(" ", "").upper()

def _check_duplicate_cf(lista: List[Dict[str, str]], cf: str, *, skip_index: int | None = None) -> bool:
    """True se esiste già un elemento con stesso Cod_fisc (case-insensitive, spazi ignorati)."""
    ncf = _norm_cf(cf)
    for i, r in enumerate(lista):
        if skip_index is not None and i == skip_index:
            continue
        if _norm_cf(r.get("Cod_fisc", "")) == ncf and ncf != "":
            return True
    return False

def _carica_posizioni() -> List[str]:
    try:
        opts = load_posizioni() or []
        return [o for o in opts if isinstance(o, str) and o.strip()]
    except Exception:
        return []


# --------------------- Preparazione colonne / righe tabella ---------------------

def _make_columns(persone: List[Dict[str, str]]):
    keys = list(persone[0].keys()) if persone else BASE_COLS
    if 'Posizione' not in keys:
        keys.insert(0, 'Posizione')
    colonne = [{'name': k, 'label': k, 'field': k, 'sortable': True} for k in keys]
    # aggiungiamo colonna/chiave interna stabile per la tabella
    colonne.insert(0, {'name': '__rowid', 'label': '#', 'field': '__rowid'})
    return keys, colonne

def _rows_for_table(lista: List[Dict[str, str]]) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for i, r in enumerate(lista):
        rr = dict(r)
        rr['__rowid'] = f"{i:06d}-{_norm_cf(r.get('Cod_fisc',''))}"
        rows.append(rr)
    return rows


# --------------------- Dialog form (con fallback posizioni) ---------------------

def _dialog_form(
    titolo: str,
    keys: List[str],
    valori: Optional[Dict[str, str]],
    on_save: Callable[[Dict[str, str]], None],
):
    dlg = ui.dialog().classes('max-h-[90vh]')
    with dlg:
        card = ui.card().classes('w-full max-w-3xl p-4 bg-white dark:bg-gray-800 rounded-xl shadow-lg')
        with card:
            ui.label(titolo).classes('text-lg font-semibold mb-3')

            form_widgets: Dict[str, ui.element] = {}
            posizioni_options = _carica_posizioni()
            current_pos = (valori.get('Posizione') if valori else None) or ""

            with ui.row().classes('items-center gap-3 mb-2'):
                ui.label('Posizione').classes('w-28 font-medium')
                if posizioni_options:
                    sel_pos = ui.select(
                        posizioni_options,
                        value=(current_pos if current_pos in posizioni_options else None),
                        label='Seleziona posizione'
                    ).props('dense outlined clearable').classes('flex-1')
                    def _refresh_posizioni():
                        sel_pos.set_options(_carica_posizioni())
                    ui.button('', icon='edit', on_click=lambda: mostra_popup_posizioni(on_update=_refresh_posizioni))\
                        .props('flat round').tooltip('Gestisci posizioni')
                    form_widgets['Posizione'] = sel_pos
                else:
                    # fallback input libero se non ci sono posizioni configurate
                    inp_pos = ui.input(label='Posizione (testo libero)', value=current_pos)\
                               .props('dense outlined clearable').classes('flex-1')
                    ui.button('', icon='edit', on_click=lambda: mostra_popup_posizioni())\
                        .props('flat round').tooltip('Gestisci posizioni')
                    form_widgets['Posizione'] = inp_pos

            grid_keys = [k for k in keys if k != 'Posizione']
            with ui.grid(columns=2).classes('gap-3'):
                for k in grid_keys:
                    form_widgets[k] = ui.input(label=k, value=(valori.get(k) if valori else ''))\
                        .props('dense outlined').classes('w-full')

            def _collect() -> Dict[str, str]:
                raw = {k: getattr(w, 'value', '') or '' for k, w in form_widgets.items()}
                return _strip_dict(raw)

            def _reset():
                for w in form_widgets.values():
                    if hasattr(w, 'value'):
                        w.value = ''
                ui.notify('Campi resettati', type='info')

            with ui.row().classes('justify-end gap-2 mt-4'):
                ui.button('Reset', on_click=_reset).props('outlined icon=refresh')

                def _salva():
                    on_save(_collect())
                    dlg.close()

                ui.button('Salva', on_click=_salva).props('icon=save color=positive')
    dlg.open()


# --------------------- Popup principale ---------------------

def mostra_popup_persone_giuridiche(callback_aggiungi: Optional[Callable[[List[Dict[str, str]]], None]] = None):
    persone = _carica_persone()
    keys, colonne = _make_columns(persone)

    dialog = ui.dialog().classes('max-h-[95vh]')
    with dialog:
        card = ui.card().classes('w-full max-w-7xl p-4 bg-white dark:bg-gray-800 rounded-xl shadow-lg')
        with card:
            with ui.row().classes('w-full items-center justify-between mb-3 p-2 bg-gray-50 dark:bg-gray-700 rounded-lg'):
                ui.label('Gestione Persone Giuridiche').classes('text-xl font-bold')
                is_full = {'v': False}
                def toggle_fullscreen():
                    if not is_full['v']:
                        dialog.props('maximized')
                        card.classes(remove='max-w-7xl')
                        is_full['v'] = True
                    else:
                        dialog.props(remove='maximized')
                        card.classes(add='max-w-7xl')
                        is_full['v'] = False
                with ui.row().classes('items-center gap-2'):
                    ui.button('', on_click=toggle_fullscreen, icon='fullscreen').props('flat round').tooltip('Allarga/Riduci')
                    ui.button('', on_click=dialog.close, icon='close').props('flat round color=negative').tooltip('Chiudi')

            ui.label('Elenco Persone Giuridiche').classes('text-base font-semibold mb-2')

            # Stato selezione tramite __rowid (stabile)
            selected_rows: List[Dict[str, str]] = []
            def on_selection(e):
                nonlocal selected_rows
                selected_rows = e.selection or []

            rows_table = _rows_for_table(persone)
            table = ui.table(
                columns=colonne,
                rows=rows_table,
                row_key='__rowid',
                selection='single',
                on_select=on_selection,
                pagination=10,
            ).classes('w-full text-sm border rounded-lg mb-3').props('dense flat bordered wrap-cells')

            def refresh_table():
                data = _carica_persone()
                table.rows = _rows_for_table(data)
                table.update()
                selected_rows.clear()

            with ui.row().classes('gap-2 mb-4 flex-wrap'):
                # MODIFICA
                def _azione_modifica():
                    if not selected_rows:
                        ui.notify('Seleziona una riga dalla tabella', type='warning'); return
                    riga_sel = selected_rows[0]
                    rowid = riga_sel.get('__rowid', '')
                    def _salva_modifica(values: Dict[str, str]):
                        lista = _carica_persone()
                        try:
                            idx = int(rowid.split('-')[0])
                        except Exception:
                            idx = -1
                        if not (0 <= idx < len(lista)):
                            ui.notify('Riga non trovata su file, impossibile aggiornare', type='negative'); return
                        values = _strip_dict(values)
                        # duplicati su Cod_fisc (ignora questo indice)
                        if _check_duplicate_cf(lista, values.get('Cod_fisc', ''), skip_index=idx):
                            ui.notify('Codice Fiscale già presente', type='warning'); return
                        lista[idx] = values
                        _salva_persone(lista)
                        ui.notify('Riga aggiornata', type='positive')
                        refresh_table()
                    _dialog_form('Modifica riga', keys, riga_sel, _salva_modifica)
                ui.button('Modifica', on_click=_azione_modifica).props('icon=edit color=secondary')

                # ELIMINA
                def _azione_elimina():
                    if not selected_rows:
                        ui.notify('Seleziona una riga dalla tabella', type='warning'); return
                    riga_sel = selected_rows[0]
                    rowid = riga_sel.get('__rowid', '')
                    def _conferma_elimina():
                        lista = _carica_persone()
                        try:
                            idx = int(rowid.split('-')[0])
                        except Exception:
                            idx = -1
                        if 0 <= idx < len(lista):
                            del lista[idx]
                            _salva_persone(lista)
                            ui.notify('Riga eliminata', type='positive')
                            refresh_table()
                        else:
                            ui.notify('Riga non trovata su file, impossibile eliminare', type='negative')

                    dlg = ui.dialog()
                    with dlg:
                        with ui.card().classes('p-4'):
                            ui.label("Confermi l'eliminazione della riga selezionata?").classes('mb-3')
                            with ui.row().classes('justify-end gap-2'):
                                ui.button('Annulla', on_click=dlg.close).props('outlined')
                                ui.button('Elimina', on_click=lambda: (_conferma_elimina(), dlg.close())).props('color=negative icon=delete')
                    dlg.open()
                ui.button('Elimina', on_click=_azione_elimina).props('icon=delete color=negative')

                # AGGIUNGI
                def _azione_aggiungi():
                    def _salva_nuova(values: Dict[str, str]):
                        values = _strip_dict(values)
                        lista = _carica_persone()
                        if _check_duplicate_cf(lista, values.get('Cod_fisc', '')):
                            ui.notify('Codice Fiscale già presente', type='warning'); return
                        lista.append(values)
                        _salva_persone(lista)
                        ui.notify('Nuova riga aggiunta', type='positive')
                        refresh_table()
                    _dialog_form('Aggiungi nuova riga', keys, None, _salva_nuova)
                ui.button('Aggiungi', on_click=_azione_aggiungi).props('icon=add color=primary')

                # PASSA AD ANAGRAFICA
                def _azione_aggiungi_ad_anagrafica():
                    if not selected_rows:
                        ui.notify('Seleziona una riga dalla tabella', type='warning'); return
                    if callable(callback_aggiungi):
                        riga = dict(selected_rows[0])
                        riga.pop('__rowid', None)
                        try:
                            callback_aggiungi([riga])
                            ui.notify('Riga passata ad Anagrafica', type='positive')
                        except Exception as e:
                            ui.notify(f'Errore nel passaggio ad Anagrafica: {e}', type='negative')
                    else:
                        ui.notify('Nessun callback di anagrafica fornito', type='warning')
                ui.button('Aggiungi ad anagrafica', on_click=_azione_aggiungi_ad_anagrafica).props('icon=person_add color=accent')

                ui.button('Gestisci posizioni', on_click=lambda: mostra_popup_posizioni()).props('icon=work')
                ui.button('Refresh', on_click=refresh_table).props('icon=refresh')

            with ui.row().classes('w-full justify-end items-center gap-2 mt-2'):
                ui.button('', on_click=lambda *_: None or toggle_fullscreen(), icon='fullscreen').props('flat round').tooltip('Allarga/Riduci')
                ui.button('Chiudi', on_click=dialog.close).props('icon=close color=negative')

    dialog.open()

