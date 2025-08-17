# apertura_pratica_popup.py — JSON-only (storico) + SQLite listing (nuovo)
from __future__ import annotations

import os
import re
import sqlite3
from datetime import datetime, date
from typing import Iterable, Tuple, Optional, Dict, Any, List
from pathlib import Path

from nicegui import ui

# --- original imports (JSON flow) ---
from log_gestione_pratica import log_apertura
from repo import write_pratica
from utils_lookup import load_id_pratiche, load_avvocati
from id_registry import load_next_id, persist_after_save
from reindex import reindex
from dual_save import dual_save

# --- new (SQLite support, solo apertura/elenco) ---
try:
    from db_core import get_connection as _get_connection
    from repo_sqlite import load_pratica as _load_pratica_db
except Exception:  # se non presenti, il tab DB verrà disabilitato
    _get_connection = None
    _load_pratica_db = None

# --- importatore SQL (per import pratica via .sql) ---
try:
    # rende disponibile import_sql se presente sotto tools
    from tools import import_sql as _import_sql
except Exception:
    # se il modulo non esiste o fallisce l'import, la funzione sarà None
    _import_sql = None

# Formato per la porzione data nel nome cartella cliente (es. _14082025)
DATA_FMT_CARTELLA = '%d%m%Y'

# DB path (se esiste il layer, altrimenti il tab rimane disattivato)
DB_PATH = os.environ.get('GP_DB_PATH', os.path.join('archivio', '0gp.sqlite'))


# ---------- Utility JSON-only ----------

def _load_avvocati_json() -> list[str]:
    try:
        lst = load_avvocati()
        return sorted({x for x in lst if isinstance(x, str) and x.strip()})
    except Exception:
        return []


def _make_id_suffix(numero: int, anno: int) -> str:
    s = f'{numero}{anno}'
    return ('0' + s) if len(s) == 5 else s


def _read_ids_for_table() -> list[dict]:
    rows = []
    try:
        for el in load_id_pratiche():
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


# ---------- Supporto ID & Collisioni (come originale) ----------

def _id_exists(numero: int, anno: int) -> Tuple[bool, Optional[str]]:
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


# ---------- Mapping DB -> stato UI (minimo, non invasivo) ----------

def _apply_db_pratica_to_state(db_pratica: Dict[str, Any], pratica_data: Dict[str, Any], anagrafica_data: Dict[str, Any]) -> None:
    """Mappa i campi principali dal record DB in pratica_data/anagrafica_data, senza cambiare struttura UI."""
    if not db_pratica:
        return
    # ID
    pid = db_pratica.get('id_pratica')
    if pid and isinstance(pid, str) and '_' in pid:
        # in DB tipicamente "1_2025"; in UI si usa "1/2025"
        try:
            n, a = pid.split('_', 1)
            pratica_data['id_pratica'] = f'{n}/{a}'
        except Exception:
            pratica_data['id_pratica'] = pid
    elif pid:
        pratica_data['id_pratica'] = pid

    # Campi principali (adatta ai nomi usati in UI originale)
    pratica_data['tipo_pratica'] = db_pratica.get('tipo_pratica')
    pratica_data['settore_pratica'] = db_pratica.get('settore')
    pratica_data['materia_pratica'] = db_pratica.get('materia')
    pratica_data['note'] = db_pratica.get('note')

    # Referente (UI usa un campo singolo testuale, qui ricaviamo dal primo avvocato con ruolo 'referente' o da 'referente_nome')
    ref_nome = db_pratica.get('referente_nome')
    ref_email = db_pratica.get('referente_email')
    avv = db_pratica.get('avvocati') or []
    if not ref_nome and avv:
        # prova a trovare il referente
        for a in avv:
            if (a.get('ruolo') or '').lower() == 'referente' and a.get('nome'):
                ref_nome = a.get('nome')
                break
        if not ref_nome and avv[0].get('nome'):
            ref_nome = avv[0]['nome']
    pratica_data['avvocato_referente'] = ref_nome or pratica_data.get('avvocato_referente')

    # Avvocati in mandato (UI tiene lista testuale; qui mettiamo una lista di nomi/email)
    in_mandato: List[str] = pratica_data.get('avvocato_in_mandato') or []
    for a in avv:
        nm = a.get('nome') or a.get('email')
        if nm and nm not in in_mandato:
            in_mandato.append(nm)
    pratica_data['avvocato_in_mandato'] = in_mandato

    # Nessuna modifica aggressiva su percorsi/cartelle: la UI originale gestisce percorso_pratica e nome_pratica.

    # Anagrafica: il DB schema standard non la dettaglia; lasciamo invariata.
    # Volendo, si potrebbe inferire da documenti o note, ma evitiamo per non “sporcare” lo stato.


# ---------- Dialog secondari (esteso: + tab DB) ----------

def _popup_elenco_pratiche() -> None:
    dlg = ui.dialog()
    with dlg, ui.card().classes('w-[900px] max-w-[95vw]'):
        ui.label('Elenco pratiche').classes('text-xl font-semibold')

        with ui.tabs().classes('w-full') as tabs:
            t_json = ui.tab('Archivio JSON')
            t_db = ui.tab('DB SQLite')

        with ui.tab_panels(tabs, value=t_json).classes('w-full'):
            # ---- Pannello JSON (originale) ----
            with ui.tab_panel(t_json):
                table_container = ui.column().classes('w-full')
                links_container = ui.column().classes('w-full mt-2')

                def render_json():
                    table_container.clear()
                    links_container.clear()
                    rows = _read_ids_for_table()
                    if not rows:
                        with table_container:
                            ui.label('Nessun dato trovato in lib_json/id_pratiche.json').classes('text-gray-500')
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

                with ui.row().classes('justify-end w-full mt-3 gap-2'):
                    ui.button('Aggiorna', on_click=render_json).props('icon=refresh')
                render_json()

            # ---- Pannello DB (nuovo) ----
            with ui.tab_panel(t_db):
                if _get_connection is None or _load_pratica_db is None or not os.path.exists(DB_PATH):
                    ui.label('Layer SQLite non disponibile o DB assente.').classes('text-red-600')
                else:
                    with ui.row().classes('items-center gap-2'):
                        filtro = ui.input('Filtro (ID, referente, tipo)').props('clearable').classes('w-[360px]')
                        limit = ui.number('Limite', value=200, min=1, max=2000, format='%d').classes('w-[120px]')
                        btn_reload = ui.button('Aggiorna').props('icon=refresh')

                    tbl_container = ui.column().classes('w-full mt-2')

                    def render_db():
                        tbl_container.clear()
                        q = (filtro.value or '').strip()
                        lim = int(limit.value or 200)
                        sql = ("SELECT id_pratica, anno, numero, tipo_pratica, referente_nome, updated_at "
                               "FROM pratiche ")
                        params: tuple = ()
                        if q:
                            sql += ("WHERE id_pratica LIKE ? OR COALESCE(referente_nome,'') LIKE ? OR "
                                    "COALESCE(tipo_pratica,'') LIKE ? ")
                            like = f"%{q}%"
                            params = (like, like, like)
                        sql += "ORDER BY updated_at DESC, id_pratica DESC LIMIT ?"
                        params += (lim,)

                        rows: List[sqlite3.Row] = []
                        try:
                            with _get_connection(DB_PATH) as con:
                                con.row_factory = sqlite3.Row
                                rows = list(con.execute(sql, params))
                        except Exception as e:
                            with tbl_container:
                                ui.label(f'Errore DB: {e}').classes('text-red-600')
                            return

                        with tbl_container:
                            with ui.row().classes('text-xs opacity-70 w-full justify-between'):
                                ui.label('ID pratica').classes('w-[160px]')
                                ui.label('Tipo').classes('w-[180px]')
                                ui.label('Referente').classes('w-[220px]')
                                ui.label('Ultimo aggiornamento').classes('w-[180px]')
                                ui.label('').classes('w-[80px]')
                            ui.separator()
                            for r in rows:
                                pid = r['id_pratica']
                                with ui.row().classes('w-full items-center justify-between'):
                                    ui.label(pid).classes('w-[160px]')
                                    ui.label(r['tipo_pratica'] or '-').classes('w-[180px]')
                                    ui.label(r['referente_nome'] or '-').classes('w-[220px]')
                                    ui.label(r['updated_at'] or '').classes('w-[180px]')

                                    def _open(pid=pid):
                                        try:
                                            rec = _load_pratica_db(pid)
                                            if not rec:
                                                ui.notify(f'Pratica {pid} non trovata nel DB', type='warning'); return
                                            # Mappa DB -> stato UI (non invasivo)
                                            _apply_db_pratica_to_state(rec, _popup_state['pratica_data'], _popup_state['anagrafica_data'])
                                            # Aggiorna UI principale e chiudi popup
                                            try:
                                                _popup_state['on_set_user_label'](_popup_state.get('user') or '')
                                            except Exception:
                                                pass
                                            ui.notify(f'Pratica {pid} caricata dal DB', type='positive')
                                            dlg.close()
                                            ui.timer(0.05, lambda: ui.navigate.reload(), once=True)
                                        except Exception as e:
                                            ui.notify(f'Errore apertura {pid}: {e}', type='negative')

                                    ui.button('Apri', on_click=_open).classes('w-[80px]').props('flat color=primary')

                    btn_reload.on('click', render_db)
                    filtro.on('keydown.enter', render_db)
                    render_db()

    dlg.open()


def _file_browser_dialog(on_pick, start_dir: str | None = None) -> None:
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


# ---------- Helpers per MODIFICA (applica JSON allo stato) ----------

def _apply_record_to_state(record: Dict[str, Any], pratica_data: Dict[str, Any], anagrafica_data: Dict[str, Any]) -> None:
    if not isinstance(record, dict):
        return
    mapping = [
        'id_pratica', 'percorso_pratica', 'data_apertura', 'data_chiusura',
        'valore_pratica', 'tipo_pratica', 'settore_pratica', 'materia_pratica',
        'note', 'nome_pratica',
    ]
    for k in mapping:
        if k in record:
            pratica_data[k] = record.get(k)
    pratica_data['avvocato_referente'] = record.get('avvocato_referente', pratica_data.get('avvocato_referente'))
    pratica_data['avvocato_in_mandato'] = record.get('avvocato_in_mandato', pratica_data.get('avvocato_in_mandato', []))
    pratica_data['preventivo_inviato'] = bool(record.get('preventivo_inviato', pratica_data.get('preventivo_inviato', False)))
    for key in ('tariffe_contenzioso', 'tariffe_stragiudiziale', 'preventivi', 'preventivi_stragiudiziale', 'scadenze'):
        if key in record:
            pratica_data[key] = record.get(key)
    if 'tipo_tariffe' in record and isinstance(record['tipo_tariffe'], list):
        pratica_data['tipo_tariffe'] = [str(x) for x in record['tipo_tariffe'] if str(x).strip()]
    ana = record.get('anagrafica') or {}
    if isinstance(ana, dict):
        fis = ana.get('persone_fisiche') or []
        giu = ana.get('persone_giuridiche') or []
        if isinstance(fis, list):
            anagrafica_data['fisiche'] = fis
        if isinstance(giu, list):
            anagrafica_data['giuridiche'] = giu


# ---------- Stato condiviso del popup (serve al tab DB per chiudere/settare UI) ----------
_popup_state: Dict[str, Any] = {
    'pratica_data': None,
    'anagrafica_data': None,
    'on_set_user_label': lambda *a, **k: None,
    'user': '',
}


# ---------- Dialog principale (firma originale, invariata) ----------

def mostra_popup_apertura(pratica_data: dict, id_predefinito: str, on_set_user_label, anagrafica_data: dict) -> None:
    # rendi disponibili al tab DB i riferimenti allo stato UI
    _popup_state['pratica_data'] = pratica_data
    _popup_state['anagrafica_data'] = anagrafica_data
    _popup_state['on_set_user_label'] = on_set_user_label

    # 0) usa il prossimo ID reale come default
    try:
        num_default, anno_default = load_next_id()
    except Exception:
        oggi = date.today()
        num_default, anno_default = (1, oggi.year)

    id_suffix = _make_id_suffix(num_default, anno_default)
    oggi_str = datetime.now().strftime(DATA_FMT_CARTELLA)

    dialog = ui.dialog().props('persistent maximized')
    with dialog, ui.card().classes('w-[95vw] h-[92vh] max-w-[98vw]').style('resize: both; overflow: auto;'):
        ui.label('Apertura / Modifica pratica').classes('text-3xl font-bold mb-2')

        # --- due colonne: [apertura] | [modifica esistente] ---
        with ui.row().classes('w-full gap-4 no-wrap items-start overflow-auto'):
            # =====================
            # COLONNA A: APERTURA
            # =====================
            with ui.column().classes('flex-1 min-w-[460px]'):
                ui.label('Nuova pratica').classes('text-lg font-semibold')
                with ui.row().classes('w-full gap-4 items-end'):
                    ui.label('ID_pratica').classes('font-medium')
                    in_num = ui.number('Numero', value=num_default, min=1, format='%d').classes('w-40').props('readonly')
                    in_anno = ui.number('Anno', value=anno_default, min=2000, format='%d').classes('w-48').props('readonly')

                ui.separator()

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

                pattern_cartella = re.compile(r'.*_\d{8}$')
                pattern_cartella_p = re.compile(r'.*_\d{6}$')

                def _append_suffix_if_missing(inp, pattern: re.Pattern, suffix: str):
                    v = (inp.value or '').strip()
                    if not v or pattern.match(v):
                        return
                    base = v.rsplit('_', 1)[0] if '_' in v else v
                    inp.value = f'{base}_{suffix}'
                    try: inp.update()
                    except Exception: pass

                def _validate_required() -> bool:
                    fields: Iterable[tuple[str, object]] = [
                        ('Nome utente', (in_user.value or '').strip() if hasattr(in_user, 'value') else ''),
                        ('Nome cartella cliente', (in_cliente.value or '').strip()),
                        ('Nome pratica', (in_pratica.value or '').strip()),
                        ('Percorso base', (in_percorso.value or '').strip()),
                    ]
                    missing = [k for k, v in fields if (isinstance(v, str) and v.strip() == '') or v in (None, '')]
                    if missing:
                        ui.notify('Compila tutti i campi: ' + ', '.join(missing), type='warning'); return False
                    if not pattern_cartella.match((in_cliente.value or '').strip()):
                        ui.notify('Il nome cartella cliente deve terminare con _######## (es. _14082025)', type='warning'); return False
                    if not pattern_cartella_p.match((in_pratica.value or '').strip()):
                        ui.notify('Il nome pratica deve terminare con _###### (es. _012025)', type='warning'); return False
                    return True

                in_cliente.on('blur', lambda e: _append_suffix_if_missing(in_cliente, pattern_cartella, oggi_str))
                in_pratica.on('blur', lambda e: _append_suffix_if_missing(in_pratica, pattern_cartella_p, id_suffix))

                with ui.row().classes('w-full justify-between mt-2'):
                    ui.button('Elenco pratiche', on_click=_popup_elenco_pratiche).props('icon=folder')
                    with ui.row().classes('gap-2'):
                        def hard_refresh(): ui.navigate.reload()

                        def salva():
                            if not _validate_required():
                                return
                            user = (in_user.value or '').strip() if hasattr(in_user, 'value') else ''
                            cartella_cliente = (in_cliente.value or '').strip()
                            cartella_pratica = (in_pratica.value or '').strip()
                            base_path = (in_percorso.value or '').strip()

                            cliente_path = os.path.join(base_path, cartella_cliente)
                            pratica_path = os.path.join(cliente_path, cartella_pratica)
                            try:
                                os.makedirs(os.path.join(pratica_path, 'log_pratica'), exist_ok=True)
                                os.makedirs(os.path.join(pratica_path, 'documenti_pratica'), exist_ok=True)
                            except Exception as e:
                                ui.notify(f'Errore creazione cartelle: {e}', type='negative'); return

                            numero, anno = load_next_id()
                            id_str = f"{numero}/{anno}"

                            esiste, nome_esistente = _id_exists(numero, anno)

                            def _prosegui(def_num: int, def_anno: int):
                                id_eff = f"{def_num}/{def_anno}"
                                pratica_data["id_pratica"] = id_eff
                                pratica_data['percorso_pratica'] = pratica_path
                                pratica_data['nome_pratica'] = cartella_pratica

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

                                try:
                                    write_pratica(folder=Path(pratica_path), data=pratica_data, actor=user or "system")
                                    persist_after_save(def_num, def_anno, pratica_data.get("nome_pratica",""), pratica_data.get("percorso_pratica",""), created_by=user)
                                    reindex(root=Path("archivio"), db_path=Path("archivio/indice.sqlite"))
                                    try:
                                        canon_path = Path(pratica_path) / 'pratica.json'
                                        js_text = canon_path.read_text(encoding='utf-8')
                                        base_id = str(pratica_data.get("id_pratica", "")).replace("/", "")
                                        base_id = re.sub(r'[^A-Za-z0-9_-]+', '', base_id)
                                        if base_id:
                                            out_ds = dual_save(
                                                pratica_folder=Path(pratica_path),
                                                backup_dir=Path("archivio/backups_json"),
                                                base_id=base_id,
                                                json_text=js_text,
                                            )
                                            from pathlib import Path as _P
                                            ui.notify(f"Copia: {_P(out_ds['timestamped_path']).name} — Backup: {_P(out_ds['backup_path']).name}", type='positive')
                                    except Exception as _e_ds:
                                        ui.notify(f"Dual-save non riuscito: {_e_ds}", type='warning')

                                except Exception as e:
                                    ui.notify(f"Errore durante il salvataggio: {e}", type="negative"); return

                                try:
                                    on_set_user_label(user)
                                except Exception:
                                    pass

                                ui.notify(f'Pratica {id_eff} creata e salvata correttamente', type='positive')
                                dialog.close()

                            if esiste and (nome_esistente or '') != cartella_pratica:
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
                                            d.close(); _prosegui(numero, anno)
                                        def _usa_prossimo():
                                            d.close(); nuovo_num = _next_id_for_year(anno); _prosegui(nuovo_num, anno)
                                        ui.button('Sovrascrivi (stesso ID)', on_click=_sovrascrivi).props('color=negative')
                                        ui.button('Usa prossimo ID', on_click=_usa_prossimo).props('color=primary')
                                        ui.button('Annulla', on_click=d.close).props('flat')
                                d.open(); return
                            else:
                                _prosegui(numero, anno)

                        ui.button('SALVA', on_click=salva).props('icon=save color=positive')
                        ui.button('', on_click=hard_refresh).props('icon=refresh flat')

            # ===========================================
            # COLONNA B: MODIFICA PRATICA ESISTENTE (carica JSON)



            # ===========================================
            with ui.column().classes('flex-1 min-w-[460px]'):
                ui.label('Modifica pratica esistente (carica JSON)').classes('text-lg font-semibold')

                # Import SQL (Carica) – come Salva
                try:
                    inject_import_sql_carica(container=ui.column().classes('mt-2'))
                except Exception as _e:
                    ui.notify(f'Import SQL non disponibile: {_e}', color='warning')

                # Import SQL (Carica) – come Salva
                try:
                    inject_import_sql_carica(container=ui.column().classes('mt-2'))
                except Exception as _e:
                    ui.notify(f'Import SQL non disponibile: {_e}', color='warning')

                status = ui.label('').classes('text-xs text-gray-600 mb-2')

                def _handle_upload(e):
                    # 1) Estrai i bytes dal payload (compat NiceGUI)
                    try:
                        payload = getattr(e, 'content', None) or getattr(e, 'file', None) or None
                        if payload is None and hasattr(e, 'files'):
                            files = e.files or []
                            if files:
                                payload = files[0].content
                        if payload is None:
                            ui.notify('Upload vuoto', color='negative'); return

                        if hasattr(payload, 'read'):
                            data = payload.read()
                        else:
                            data = payload

                        text = data.decode('utf-8') if isinstance(data, (bytes, bytearray)) else str(data)
                        import json
                        record = json.loads(text)
                    except Exception as exc:
                        ui.notify(f'Caricamento fallito: {exc}', color='negative'); return

                    # 2) Persisti nello storage utente
                    try:
                        from nicegui import app as _app_
                        _app_.storage.general['pratica_loaded_record'] = record
                    except Exception:
                        pass

                    # 3) Applica allo stato
                    _apply_record_to_state(record, pratica_data, anagrafica_data)
                    status.text = 'File caricato correttamente'; status.update()
                    ui.notify('Dati caricati nella pratica', color='positive')

                    # 4) Aggiorna UI collegata e chiudi popup
                    try:
                        pratica_data.get('refresh_pratica', lambda: None)()
                    except Exception:
                        pass
                    for k in ('refresh_settori', 'refresh_materie', 'refresh_avvocati'):
                        try:
                            pratica_data.get(k, lambda: None)()
                        except Exception:
                            pass
                    ui.notify('Pratica caricata: interfaccia aggiornata', type='positive')
                    try:
                        dialog.close()
                    except Exception:
                        pass
                    try:
                        ui.timer(0.05, lambda: ui.navigate.reload(), once=True)
                    except Exception:
                        pass

                ui.upload(label='Seleziona file JSON', on_upload=_handle_upload).props('accept=.json').classes('mb-2')

                path_state: Dict[str, Any] = {'path': ''}
                ui.input('Oppure percorso file JSON sul server', placeholder='/percorso/pratica/9_2025_gp_11082025_170314.json').bind_value(path_state, 'path').classes('w-full mb-2')

                def _load_from_path():
                    p = Path((path_state.get('path') or '').strip())
                    if not p.exists():
                        ui.notify('Percorso non trovato', color='negative'); return
                    try:
                        text = p.read_text(encoding='utf-8')
                        import json
                        record = json.loads(text)
                    except Exception as exc:
                        ui.notify(f'JSON non valido: {exc}', color='negative'); return
                    _apply_record_to_state(record, pratica_data, anagrafica_data)
                    ui.notify('Dati caricati dalla path', color='positive')

                    try:
                        pratica_data.get('refresh_pratica', lambda: None)()
                    except Exception:
                        pass
                    for k in ('refresh_settori', 'refresh_materie', 'refresh_avvocati'):
                        try:
                            pratica_data.get(k, lambda: None)()
                        except Exception:
                            pass
                    ui.notify('Pratica caricata: interfaccia aggiornata', type='positive')
                    try:
                        dialog.close()
                    except Exception:
                        pass
                    try:
                        ui.timer(0.05, lambda: ui.navigate.reload(), once=True)
                    except Exception:
                        pass

                with ui.row().classes('gap-2 mb-2'):
                    ui.button('Carica da percorso', on_click=_load_from_path).props('icon=folder_open color=primary flat')
                    ui.button('Apri cartella pratica', on_click=lambda: _open_path(pratica_data.get('percorso_pratica', ''))).props('icon=folder flat')

                # Azione di import SQL: disponibile solo se il modulo è presente e il DB esiste
                # Questa funzionalità consente di applicare uno script .sql generato dall'export
                # a un database esistente. L'upload accetta file con estensione .sql. Una volta
                # completato l'import, viene ricaricata l'interfaccia per aggiornare l'elenco
                # delle pratiche. Eventuali errori vengono mostrati tramite notifica.
                if _import_sql is not None:
                    def _handle_sql_upload(e):
                        try:
                            # Estrai i bytes dal payload dell'upload (NiceGUI fornisce diversi campi a seconda della versione)
                            payload = getattr(e, 'content', None) or getattr(e, 'file', None) or None
                            if payload is None and hasattr(e, 'files'):
                                files = e.files or []
                                if files:
                                    payload = files[0].content
                            if payload is None:
                                ui.notify('Upload vuoto', color='negative'); return

                            if hasattr(payload, 'read'):
                                data = payload.read()
                            else:
                                data = payload
                            if not data:
                                ui.notify('Nessun contenuto nel file', color='negative'); return

                            # Salva il contenuto in un file temporaneo
                            import tempfile, uuid
                            tmp_dir = tempfile.gettempdir()
                            tmp_name = f"import_{uuid.uuid4().hex}.sql"
                            tmp_path = os.path.join(tmp_dir, tmp_name)
                            with open(tmp_path, 'wb') as f:
                                if isinstance(data, str):
                                    f.write(data.encode('utf-8'))
                                else:
                                    f.write(data)

                            # Esegui l'import: DB_PATH definito a livello di modulo
                            try:
                                stats = _import_sql(DB_PATH, tmp_path)  # type: ignore[call-arg]
                            except Exception as exc:
                                ui.notify(f'Import SQL fallito: {exc}', color='negative'); return

                            # Notifica esito positivo
                            msg = f"Import SQL completato: {stats.get('changes', 0)} modifiche"
                            if stats.get('tables'):
                                msg += f" su tabelle {', '.join(stats['tables'])}"
                            ui.notify(msg, color='positive')

                            # Ricarica l'elenco pratiche e UI
                            try:
                                ui.navigate.reload()
                            except Exception:
                                pass
                        except Exception as exc:
                            ui.notify(f'Errore durante l\'import: {exc}', color='negative')

                    ui.upload(label='Importa da SQL', on_upload=_handle_sql_upload).props('accept=.sql').classes('mb-2')

                with ui.column().classes('gap-1 mt-2'):
                    ui.label().bind_text_from(pratica_data, 'id_pratica', lambda v: f'ID pratica: {v or "(n/d)"}').classes('text-sm')
                    ui.label().bind_text_from(pratica_data, 'percorso_pratica', lambda v: f'Cartella: {v or "(non impostata)"}').classes('text-sm')

        # Fine due colonne

    dialog.open()







def inject_import_sql_carica(*, container) -> None:
    """Da chiamare DENTRO la sezione 'Modifica pratica esistente'.
    Aggiunge upload .sql + bottone 'Carica' che, come 'Salva', chiude Apertura pratica e apre Gestione pratiche.
    """
    from typing import Optional
    import asyncio, os, re
    from pathlib import Path
    try:
        from sql_import import import_pratica_sql  # (changed: bool, id_raw: Optional[str])
    except Exception:
        import_pratica_sql = None

    def _gp_read_text(path: Path) -> str:
        try:
            return path.read_text(encoding='utf-8', errors='ignore')
        except Exception:
            return path.read_text(errors='ignore')

    def _gp_hint_id(sql_text: str) -> Optional[str]:
        m = re.search(r"Export pratica\s+([^\s]+)", sql_text)
        if m:
            return m.group(1).strip()
        m = re.search(r"WHERE\s+(?:id_pratica|pratica_id)\s*=\s*'([^']+)'", sql_text, re.IGNORECASE)
        return m.group(1).strip() if m else None

    async def _gp_import_and_navigate(sql_text: str, id_hint: Optional[str] = None) -> None:
        from nicegui import ui
        if import_pratica_sql is None:
            ui.notify('Import SQL non disponibile (manca sql_import.py)', color='negative', close_button='✖')
            return
        db_path = os.environ.get('GP_DB_PATH', str(Path('archivio') / '0gp.sqlite'))
        changed, id_raw = await asyncio.to_thread(import_pratica_sql, db_path, sql_text)
        focus_id = id_raw or id_hint

        if changed:
            ui.notify('Import completato', color='positive')
        else:
            ui.notify('Import eseguito: nessuna modifica rilevata', color='warning')

        # prova funzioni di navigazione "come Salva"
        for name in ['vai_a_gestione_pratiche','go_to_gestione_pratiche','apri_gestione_pratiche','open_gestione_pratiche',
                     '_vai_a_gestione_pratiche','_open_gestione_pratiche','chiudi_e_apri_gestione_pratiche']:
            fn = globals().get(name)
            if callable(fn):
                try:
                    return fn(focus_id) if focus_id is not None else fn()
                except TypeError:
                    try: return fn()
                    except Exception: pass

        # fallback
        target = '/gestione_pratiche'
        if focus_id:
            try:
                from urllib.parse import quote
                target = f'{target}?import={quote(str(focus_id))}'
            except Exception:
                pass
            ui.run_javascript(f"localStorage.setItem('gp_last_import','{str(focus_id)}');")
        ui.open(target)

    from nicegui import ui
    state = {'sql_text': None, 'id_hint': None}
    with container:
        ui.separator()
        ui.label('Importa SQL').classes('text-sm text-gray-500')

        upload = ui.upload(
            label='Seleziona file .sql',
            auto_upload=True,
            max_files=1
        ).props('accept=.sql')

        carica_btn = ui.button('Carica').props('color=primary')
        carica_btn.disable()

        async def _on_uploaded(e):
            try:
                path = None
                if hasattr(e, 'content') and hasattr(e.content, 'path'):
                    path = Path(e.content.path)
                elif hasattr(e, 'files') and e.files:
                    blob = e.files[0].content.read()
                    tmp = Path(f'__tmp_import_{ui.utils.random_string(8)}.sql')
                    tmp.write_bytes(blob)
                    path = tmp

                if path and path.exists():
                    sql_text = _gp_read_text(path)
                else:
                    data = getattr(e, 'content', None)
                    if data and hasattr(data, 'read'):
                        sql_text = data.read().decode('utf-8', errors='ignore')
                    else:
                        from nicegui import ui
                        ui.notify('Impossibile leggere il file SQL', color='negative', close_button='✖')
                        return

                state['sql_text'] = sql_text
                state['id_hint'] = _gp_hint_id(sql_text)
                carica_btn.enable()
                from nicegui import ui
                ui.notify('File SQL caricato. Premi "Carica" per importare.', color='primary')

            except Exception as ex:
                from nicegui import ui
                ui.notify(f'Errore caricamento SQL: {ex}', color='negative', close_button='✖')

        upload.on('uploaded', _on_uploaded)
        async def _on_carica():
            from nicegui import ui
            if not state['sql_text']:
                ui.notify('Nessun file SQL caricato', color='warning')
                return
            carica_btn.disable()
            try:
                await _gp_import_and_navigate(state['sql_text'], id_hint=state['id_hint'])
            except Exception as ex:
                ui.notify(f'Errore durante import SQL: {ex}', color='negative', close_button='✖')
            finally:
                carica_btn.enable()

def inject_import_sql_carica(*, container) -> None:
    """Da chiamare DENTRO la sezione 'Modifica pratica esistente'.
    Upload .sql + bottone 'Carica' che, come 'Salva', chiude Apertura pratica e apre Gestione pratiche.
    """
    from typing import Optional
    import asyncio, os, re
    from pathlib import Path
    from nicegui import ui
    try:
        from sql_import import import_pratica_sql  # (changed: bool, id_raw: Optional[str])
    except Exception:
        import_pratica_sql = None

    def _gp_read_text(path: Path) -> str:
        try:
            return path.read_text(encoding='utf-8', errors='ignore')
        except Exception:
            return path.read_text(errors='ignore')

    def _gp_hint_id(sql_text: str) -> Optional[str]:
        m = re.search(r"Export pratica\s+([^\s]+)", sql_text)
        if m:
            return m.group(1).strip()
        m = re.search(r"WHERE\s+(?:id_pratica|pratica_id)\s*=\s*'([^']+)'", sql_text, re.IGNORECASE)
        return m.group(1).strip() if m else None

    async def _gp_import_and_navigate(sql_text: str, id_hint: Optional[str] = None) -> None:
        if import_pratica_sql is None:
            ui.notify('Import SQL non disponibile (manca sql_import.py)', color='negative', close_button='✖')
            return
        db_path = os.environ.get('GP_DB_PATH', str(Path('archivio') / '0gp.sqlite'))
        changed, id_raw = await asyncio.to_thread(import_pratica_sql, db_path, sql_text)
        focus_id = id_raw or id_hint
        if changed:
            ui.notify('Import completato', color='positive')
        else:
            ui.notify('Import eseguito: nessuna modifica rilevata', color='warning')

        # Navigazione "come Salva"
        for name in ['vai_a_gestione_pratiche','go_to_gestione_pratiche','apri_gestione_pratiche','open_gestione_pratiche',
                     '_vai_a_gestione_pratiche','_open_gestione_pratiche','chiudi_e_apri_gestione_pratiche']:
            fn = globals().get(name)
            if callable(fn):
                try:
                    return fn(focus_id) if focus_id is not None else fn()
                except TypeError:
                    try:
                        return fn()
                    except Exception:
                        pass

        # Fallback: querystring + localStorage
        target = '/gestione_pratiche'
        if focus_id:
            try:
                from urllib.parse import quote
                target = f'{target}?import={quote(str(focus_id))}'
            except Exception:
                pass
            ui.run_javascript(f"localStorage.setItem('gp_last_import','{str(focus_id)}');")
        ui.open(target)

    state = {'sql_text': None, 'id_hint': None}
    with container:
        ui.separator()
        ui.label('Importa SQL').classes('text-sm text-gray-500')

        upload = ui.upload(
            label='Seleziona file .sql',
            auto_upload=True,
            max_files=1
        ).props('accept=.sql')

        carica_btn = ui.button('Carica').props('color=primary')
        carica_btn.disable()

        async def _on_uploaded(e):
            try:
                path = None
                if hasattr(e, 'content') and hasattr(e.content, 'path'):
                    path = Path(e.content.path)
                elif hasattr(e, 'files') and e.files:
                    blob = e.files[0].content.read()
                    tmp = Path(f'__tmp_import_{ui.utils.random_string(8)}.sql')
                    tmp.write_bytes(blob)
                    path = tmp

                if path and path.exists():
                    sql_text = _gp_read_text(path)
                else:
                    data = getattr(e, 'content', None)
                    if data and hasattr(data, 'read'):
                        sql_text = data.read().decode('utf-8', errors='ignore')
                    else:
                        ui.notify('Impossibile leggere il file SQL', color='negative', close_button='✖')
                        return

                state['sql_text'] = sql_text
                state['id_hint'] = _gp_hint_id(sql_text)
                carica_btn.enable()
                ui.notify('File SQL caricato. Premi \"Carica\" per importare.', color='primary')

            except Exception as ex:
                ui.notify(f'Errore caricamento SQL: {ex}', color='negative', close_button='✖')

        upload.on('uploaded', _on_uploaded)

        async def _on_carica(_=None):
            if not state['sql_text']:
                ui.notify('Nessun file SQL caricato', color='warning')
                return
            carica_btn.disable()
            try:
                await _gp_import_and_navigate(state['sql_text'], id_hint=state['id_hint'])
            except Exception as ex:
                ui.notify(f'Errore durante import SQL: {ex}', color='negative', close_button='✖')
            finally:
                carica_btn.enable()

        carica_btn.on('click', _on_carica)
