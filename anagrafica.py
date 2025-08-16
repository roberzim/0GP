"""
Modulo: anagrafica.py (patched)
Gestisce la scheda 'Anagrafica' per persone fisiche e giuridiche.
Migliorie:
  - Stato vuoto e contatori
  - Callback opzionale on_change per notificare modifiche (es. salvataggio/dirty flag)
  - Stile pulsanti uniforme
"""
from __future__ import annotations
from typing import Callable, Optional, Dict, List
from nicegui import ui
from persone_fisiche_popup_def import mostra_popup_persone_fisiche
from persone_giuridiche_popup_def import mostra_popup_persone_giuridiche


def gestisci_tab_anagrafica(anagrafica_data: dict, on_change: Optional[Callable[[], None]] = None) -> ui.column:
    """
    Costruisce la UI per la scheda 'Anagrafica' con la gestione di persone fisiche e giuridiche.

    Args:
        anagrafica_data: dict con chiavi 'fisiche' e 'giuridiche' (liste di dict).
        on_change: callback opzionale invocata dopo modifiche (aggiunte/eliminazioni).

    Returns:
        ui.column: contenitore principale per eventuali refresh.
    """
    # garantisci struttura
    anagrafica_data.setdefault('fisiche', [])
    anagrafica_data.setdefault('giuridiche', [])

    def _call_on_change():
        try:
            if on_change:
                on_change()
        except Exception:
            # la UI non deve rompersi per errori nel callback
            pass

    # --- azioni ---
    def aggiungi_anagrafica(tipo: str, righe: List[Dict]):
        anagrafica_data[tipo].extend(righe or [])
        refresh_anagrafica()
        _call_on_change()

    def elimina_riga(tipo: str, idx: int):
        if 0 <= idx < len(anagrafica_data[tipo]):
            anagrafica_data[tipo].pop(idx)
            refresh_anagrafica()
            _call_on_change()

    # --- render ---
    def _section_title(label: str, count: int):
        with ui.row().classes('items-center gap-2 mt-4'):
            ui.label(label).classes('font-bold')
            ui.chip(str(count)).props('color=primary text-color=white')

    def render_tabella(tipo: str):
        rows = anagrafica_data.get(tipo) or []
        titolo = 'Persone Fisiche' if tipo == 'fisiche' else 'Persone Giuridiche'
        _section_title(f'{titolo} aggiunte', len(rows))

        if not rows:
            ui.label(f'Nessuna {("persona fisica" if tipo == "fisiche" else "persona giuridica")} inserita.').classes('text-gray-500')
            return

        for idx, riga in enumerate(rows):
            with ui.row().classes('gap-3 items-center py-1 hover:bg-gray-50 rounded px-2'):
                # mostra coppie chiave:valore in piccolo
                for key, value in (riga or {}).items():
                    ui.label(f'{key}: {value}').classes('text-[0.9rem]')
                ui.button('Elimina', on_click=lambda i=idx: elimina_riga(tipo, i)).props('icon=delete color=negative flat').classes('ml-auto')

    # --- header azioni ---
    with ui.row().classes('gap-2 mb-2'):
        ui.button('Inserisci persone fisiche',
                  on_click=lambda: mostra_popup_persone_fisiche(callback_aggiungi=lambda righe: aggiungi_anagrafica('fisiche', righe))).props('icon=person_add color=primary')

        ui.button('Inserisci persone giuridiche',
                  on_click=lambda: mostra_popup_persone_giuridiche(callback_aggiungi=lambda righe: aggiungi_anagrafica('giuridiche', righe))).props('icon=domain_add color=primary')

    # --- contenitore principale ---
    tab_anagrafica_container = ui.column().classes('w-full')

    def refresh_anagrafica():
        tab_anagrafica_container.clear()
        with tab_anagrafica_container:
            render_tabella('fisiche')
            render_tabella('giuridiche')

    refresh_anagrafica()
    return tab_anagrafica_container
