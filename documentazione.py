# documentazione.py (patched)
# Tab 'DOCUMENTAZIONE' migliorata con fix di robustezza:
# - on_click: lambda resilienti a versioni NiceGUI che non passano argomenti
# - upload: gestione sia bytes sia file-like
# - reindex post-upload: default coerente con indice centrale 'archivio/indice.sqlite'
# - import duplicati rimossi

from __future__ import annotations
from nicegui import ui
from pathlib import Path
import os
from typing import List, Dict, Optional
from datetime import datetime

from reindex import reindex  # reindex post-upload documenti

DOCS_SUBDIR = 'documenti_pratica'


def _safe_reindex_after_upload(root: Path | str = None, db_path: Path | str = None) -> None:
    """Esegue reindex in modo sicuro dopo l'upload.
    Di default usa l'indice centrale 'archivio/indice.sqlite'."""
    try:
        root_p = Path(root) if root else Path('archivio')
        db_p = Path(db_path) if db_path else Path('archivio/indice.sqlite')
        reindex(root_p, db_p, purge=False)
    except Exception as e:
        print(f'[WARN] reindex post-upload fallito: {e}')


# ---------------- utils ----------------
def _open_path(path: str) -> None:
    """Apre un file o una cartella sul SISTEMA dove gira il server."""
    try:
        if os.name == 'nt':
            os.startfile(path)  # type: ignore
        elif os.name == 'posix':
            # Linux / macOS
            ret = os.system(f'xdg-open "{path}" >/dev/null 2>&1')
            if ret != 0:
                os.system(f'open "{path}" >/dev/null 2>&1')
        else:
            raise RuntimeError('Sistema non supportato')
    except Exception as e:
        ui.notify(f'Impossibile aprire: {e}', type='warning')


def _fmt_size(n: int) -> str:
    step = 1024.0
    units = ['B', 'KB', 'MB', 'GB', 'TB']
    s = float(n)
    for u in units:
        if s < step:
            return f"{s:.1f} {u}" if u != 'B' else f"{int(s)} {u}"
        s /= step
    return f"{s:.1f} PB"


def _fmt_dt(ts: float) -> str:
    try:
        return datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M')
    except Exception:
        return ''


def _scan_documenti(pratica_path: Path) -> List[Dict]:
    """Raccoglie i file sotto <pratica_path>/documenti_pratica con metadati utili."""
    docs_dir = pratica_path / DOCS_SUBDIR
    rows: List[Dict] = []
    if not docs_dir.exists():
        return rows
    files = [f for f in docs_dir.rglob('*') if f.is_file()]
    for f in files:
        try:
            st = f.stat()
            rows.append({
                'LINK_PATH': str(f),
                'DIR': f.parent.name,
                'FILE': f.name,
                'EXT': f.suffix.lower(),
                'SIZE': st.st_size,
                'SIZE_H': _fmt_size(st.st_size),
                'MTIME': st.st_mtime,
                'MTIME_H': _fmt_dt(st.st_mtime),
            })
        except Exception:
            rows.append({
                'LINK_PATH': str(f),
                'DIR': f.parent.name,
                'FILE': f.name,
                'EXT': f.suffix.lower(),
                'SIZE': 0,
                'SIZE_H': '',
                'MTIME': 0.0,
                'MTIME_H': '',
            })
    return rows


# ---------------- UI ----------------
def costruisci_tab_documentazione(pratica_data: dict) -> None:
    """Tab DOCUMENTAZIONE con ricerca, filtri, ordinamento e azioni."""
    # Stato
    all_documents: List[Dict] = []
    current_search: str = ''
    current_ext: str = 'Tutti'
    current_sort: str = 'Data (nuovi prima)'  # non usato esternamente ma utile se estendi

    pratica_base = (pratica_data.get('percorso_pratica') or '').strip()
    pratica_path = Path(pratica_base) if pratica_base else None

    with ui.card().classes('w-full shadow-sm border border-gray-200'):
        # Header con titolo e azioni cartella
        with ui.row().classes('items-center justify-between w-full p-4'):
            ui.label('Documenti Pratica').classes('text-xl font-bold text-gray-800')
            with ui.row().classes('items-center gap-2'):
                info = ui.label('').classes('text-sm text-gray-500')
                ui.button(
                    'Apri pratica',
                    on_click=(lambda p=pratica_base: (_open_path(p) if p else ui.notify('Nessun percorso pratica', type='warning')))
                ).props('icon=folder_open outline').classes('bg-white hover:bg-gray-50')
                ui.button(
                    f'Apri {DOCS_SUBDIR}',
                    on_click=(lambda base=pratica_path: _ensure_and_open_docs(base))
                ).props('icon=folder outline').classes('bg-white hover:bg-gray-50')
                ui.button('Aggiorna', on_click=lambda: _refresh())                     .props('icon=refresh outline')                     .classes('bg-white hover:bg-gray-50')

        # Barra strumenti: ricerca, filtro ext, ordinamento, upload
        with ui.row().classes('w-full px-4 pb-2 items-center gap-2'):
            search_input = ui.input(placeholder='Cerca documenti...')                 .props('outlined dense clearable')                 .classes('w-full')                 .on('keydown.enter', lambda: _update_search())                 .on('blur', lambda: _update_search())

            ext_select = ui.select(['Tutti'], value='Tutti', label='Estensione')                 .props('dense outlined')                 .classes('w-40')

            sort_select = ui.select(
                ['Data (nuovi prima)', 'Data (vecchi prima)', 'Nome file', 'Cartella', 'Dimensione'],
                value='Data (nuovi prima)', label='Ordina per'
            ).props('dense outlined').classes('w-56')

            # Upload in documenti_pratica
            upload = ui.upload(
                on_upload=lambda e, base=pratica_path: _handle_upload(e, base),
                auto_upload=True
            ).props('accept=*').classes('hidden')
            ui.button('Carica file', on_click=lambda: upload.run_method('pickFiles'))                 .props('icon=upload color=positive')                 .classes('shadow-sm')

        # Contenitore tabella
        table_container = ui.column().classes('w-full max-h-[60vh] overflow-auto')

        # ---- funzioni interne di stato/render ----
        def _ensure_and_open_docs(base: Optional[Path]):
            if not base:
                ui.notify('Nessun percorso pratica', type='warning'); return
            docs = base / DOCS_SUBDIR
            try:
                docs.mkdir(parents=True, exist_ok=True)
                _open_path(str(docs))
            except Exception as e:
                ui.notify(f'Errore apertura cartella: {e}', type='negative')

        def _update_search():
            nonlocal current_search
            current_search = search_input.value or ''
            _render_filtered()

        def _handle_upload(e, base: Optional[Path]):
            if not base:
                ui.notify('Nessun percorso pratica', type='warning'); return
            docs = base / DOCS_SUBDIR
            try:
                docs.mkdir(parents=True, exist_ok=True)
            except Exception as ex:
                ui.notify(f'Impossibile creare {DOCS_SUBDIR}: {ex}', type='negative'); return
            try:
                for up in e.files:
                    target = docs / up.name
                    # up.content può essere bytes o file-like
                    data = None
                    try:
                        data = up.content.read()
                    except Exception:
                        data = up.content  # bytes
                    if isinstance(data, str):
                        data = data.encode('utf-8', errors='ignore')
                    with open(target, 'wb') as f:
                        f.write(data or b'')
                ui.notify('Upload completato', type='positive')
                _safe_reindex_after_upload()
                _refresh()
            except Exception as ex:
                ui.notify(f'Upload fallito: {ex}', type='negative')

        def _render_filtered():
            if not all_documents:
                _render_rows([])
                info.text = '0 documenti'; info.update()
                return

            # filtro per ricerca
            q = (current_search or '').lower()
            rows = [d for d in all_documents if (not q) or (q in d['FILE'].lower() or q in d['DIR'].lower() or q in d['LINK_PATH'].lower())]

            # filtro per estensione
            if current_ext and current_ext != 'Tutti':
                rows = [d for d in rows if d['EXT'] == current_ext]

            # ordinamento
            sort_by = sort_select.value
            reverse = True
            if sort_by == 'Data (nuovi prima)':
                key = lambda r: r['MTIME']; reverse = True
            elif sort_by == 'Data (vecchi prima)':
                key = lambda r: r['MTIME']; reverse = False
            elif sort_by == 'Nome file':
                key = lambda r: r['FILE'].lower(); reverse = False
            elif sort_by == 'Cartella':
                key = lambda r: (r['DIR'].lower(), r['FILE'].lower()); reverse = False
            else:  # Dimensione
                key = lambda r: r['SIZE']; reverse = True
            rows.sort(key=key, reverse=reverse)

            _render_rows(rows)
            try:
                info.text = f"{len(all_documents)} documenti totali — {len(rows)} visibili"
                info.update()
            except Exception:
                pass

        def _copy_to_clipboard(text: str):
            try:
                ui.run_javascript(f"navigator.clipboard.writeText({text!r});")
                ui.notify('Percorso copiato negli appunti', type='positive')
            except Exception:
                ui.notify('Copia negli appunti non supportata', type='warning')

        def _render_rows(rows: List[Dict]):
            table_container.clear()
            with table_container:
                if not rows:
                    with ui.card().classes('w-full bg-gray-50 text-center py-8'):
                        ui.icon('folder_off', size='xl').classes('text-gray-400 mb-2')
                        if current_search:
                            ui.label('Nessun documento corrisponde alla ricerca').classes('text-gray-500')
                        else:
                            ui.label('Nessun documento trovato').classes('text-gray-500')
                    return

                # Header tabella
                with ui.grid(columns=6).classes('w-full'):
                    ui.label('File').classes('font-medium text-gray-700 p-2 bg-gray-100')
                    ui.label('Cartella').classes('font-medium text-gray-700 p-2 bg-gray-100')
                    ui.label('Percorso').classes('font-medium text-gray-700 p-2 bg-gray-100')
                    ui.label('Dim.').classes('font-medium text-gray-700 p-2 bg-gray-100')
                    ui.label('Modificato').classes('font-medium text-gray-700 p-2 bg-gray-100')
                    ui.label('Azioni').classes('font-medium text-gray-700 p-2 bg-gray-100')

                    for r in rows:
                        full = r['LINK_PATH']; dirname = r['DIR']; fname = r['FILE']
                        ext = r['EXT']; size_h = r['SIZE_H']; mtime_h = r['MTIME_H']

                        # File
                        with ui.row().classes('items-center gap-2 p-2 border-b'):
                            icon = 'description'
                            if ext in ['.pdf']: icon = 'picture_as_pdf'
                            elif ext in ['.xls', '.xlsx']: icon = 'table_chart'
                            elif ext in ['.jpg', '.jpeg', '.png', '.gif']: icon = 'image'
                            ui.icon(icon, size='sm').classes('text-green-600')
                            ui.label(fname).classes('truncate')

                        # Cartella
                        with ui.row().classes('items-center gap-2 p-2 border-b'):
                            ui.icon('folder', size='sm').classes('text-amber-600')
                            ui.label(dirname).classes('truncate')

                        # Percorso (cliccabile)
                        with ui.row().classes('items-center gap-2 p-2 border-b'):
                            ui.icon('insert_link', size='sm').classes('text-blue-600')
                            ui.button(full, on_click=(lambda p=full: _open_path(p)))                                 .props('flat color=primary').classes('text-left truncate')

                        # Dimensione
                        ui.label(size_h).classes('p-2 border-b text-right')

                        # Data mod.
                        ui.label(mtime_h).classes('p-2 border-b text-right')

                        # Azioni
                        with ui.row().classes('items-center gap-2 p-2 border-b'):
                            ui.button('', icon='open_in_new', on_click=(lambda p=full: _open_path(p))).props('flat')
                            ui.button('', icon='content_copy', on_click=(lambda p=full: _copy_to_clipboard(p))).props('flat')
                            ui.button('', icon='folder_open', on_click=(lambda p=full: _open_path(str(Path(p).parent)))).props('flat')

        def _refresh():
            nonlocal all_documents, current_ext
            if not pratica_path:
                all_documents = []
                _render_filtered()
                return
            all_documents = _scan_documenti(pratica_path)
            # aggiorna lista estensioni
            exts = sorted({r['EXT'] for r in all_documents if r['EXT']})
            options = ['Tutti'] + exts
            try:
                ext_select.options = options
                if current_ext not in options:
                    current_ext = 'Tutti'
                ext_select.value = current_ext
                ext_select.update()
            except Exception:
                pass
            _render_filtered()

        # Bind dei select al render
        ext_select.on('update:model-value', lambda e: (_set_ext(ext_select.value), _render_filtered()))
        sort_select.on('update:model-value', lambda e: _render_filtered())

        def _set_ext(value: str):
            nonlocal current_ext
            current_ext = value or 'Tutti'

        # Primo caricamento
        ui.timer(0.1, _refresh, once=True)
