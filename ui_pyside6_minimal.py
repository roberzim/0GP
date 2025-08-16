# utils.py — JSON-only helpers per NiceGUI
from __future__ import annotations

from typing import List, Any, Optional, Callable, Dict
from pathlib import Path
import os

from nicegui import ui

# Loader JSON centralizzati (lib_json/*.json)
from utils_lookup import (
    load_avvocati,
    load_posizioni,
    load_materie,
    load_settori,
    load_tariffe,
    load_tipo_pratica,
)

# ---------------------------
# Notifiche & util comuni
# ---------------------------

_NOTIFIED: set[str] = set()

def safe_notify(msg: str, *, type: str = 'info') -> None:
    """Mostra ui.notify senza esplodere se la UI non è inizializzata."""
    try:
        ui.notify(msg, type=type)
    except Exception:
        # Nessuna UI attiva (per esempio in test/headless): ignora
        pass

def notify_once(key: str, msg: str, *, type: str = 'info') -> None:
    """Mostra una notifica una sola volta per chiave."""
    if key in _NOTIFIED:
        return
    _NOTIFIED.add(key)
    safe_notify(msg, type=type)

def fmt_eur(x: Any) -> str:
    """Formatta un numero come euro stile IT (1.234,56)."""
    try:
        val = float(str(x).strip().replace('€', '').replace(' ', '').replace(',', '.'))
        s = f'{val:,.2f}'
        return s.replace(',', 'X').replace('.', ',').replace('X', '.')
    except Exception:
        return '0,00'

def parse_eur(x: Any) -> float:
    """Parsa stringhe tipo '€ 1.234,56' in float 1234.56."""
    if x is None:
        return 0.0
    s = str(x).strip().replace('€', '').replace(' ', '')
    if ',' in s and '.' in s:
        s = s.replace('.', '').replace(',', '.')
    else:
        s = s.replace(',', '.')
    try:
        return float(s)
    except Exception:
        return 0.0

def open_path(path: str) -> None:
    """Apre una cartella o un file con l’app di sistema."""
    try:
        if not path:
            raise RuntimeError('Percorso vuoto')
        if os.name == 'nt':
            os.startfile(path)  # type: ignore[attr-defined]
        elif os.name == 'posix':
            # Linux / macOS
            if os.system(f'xdg-open "{path}" >/dev/null 2>&1') != 0:
                os.system(f'open "{path}" >/dev/null 2>&1')
        else:
            raise RuntimeError('Sistema non supportato')
    except Exception as e:
        safe_notify(f'Impossibile aprire: {e}', type='warning')

# ---------------------------
# Back-compat / shim functions
# ---------------------------

def carica_avvocati() -> List[str]:
    """Shim JSON-only: restituisce la lista avvocati da lib_json/avvocati.json."""
    try:
        return list(load_avvocati())
    except Exception:
        return []

def carica_dati_xml(file_path: str, tag: str) -> List[Any]:
    """
    **DEPRECATO (JSON-only):** esiste solo per retro-compatibilità.
    Restituisce sempre una lista vuota e avvisa una sola volta.
    Sostituire con i loader di utils_lookup:
      - load_materie(), load_settori(), load_tariffe(), load_tipo_pratica(), load_posizioni(), ecc.
    """
    notify_once(
        'carica_dati_xml',
        'carica_dati_xml è deprecata (runtime JSON-only). Usa i loader di utils_lookup.',
        type='warning',
    )
    return []

# ---------------------------
# Stile/UI helpers
# ---------------------------

def stile_popup() -> None:
    """Applica stile coerente a tutti i popup."""
    ui.add_head_html('''
    <style>
        .popup-card {
            min-width: 800px;
            max-height: 90vh;
            overflow-y: auto;
        }
        .popup-header {
            font-size: 1.5rem;
            font-weight: bold;
            margin-bottom: 1rem;
            color: #1e40af;
            border-bottom: 1px solid #e5e7eb;
            padding-bottom: 0.5rem;
        }
        .popup-button {
            min-width: 100px;
            margin: 0 0.25rem;
        }
        .popup-table {
            min-width: 300px;
            max-height: 400px;
            overflow-y: auto;
        }
    </style>
    ''')

def crea_pulsanti_controllo(dialog, card_element: Optional[Any] = None) -> None:
    """
    Crea pulsanti standard per i popup (Chiudi, Ingrandisci/Riduci).
    - se possibile usa dialog.props('maximized') / remove
    - altrimenti fallback: modifica inline style del card
    """
    state = {'full': False}

    def toggle_size():
        state['full'] = not state['full']
        try:
            if state['full']:
                dialog.props('maximized')
                if card_element is not None:
                    # rimuovi eventuali limiti stretti
                    card_element.style('min-width: 80vw; width: 90vw; height: 90vh; max-width: none;')
            else:
                dialog.props(remove='maximized')
                if card_element is not None:
                    card_element.style('min-width: 600px; width: auto; max-width: 800px; height: auto;')
        except Exception:
            # fallback solo su card
            if card_element is not None:
                if state['full']:
                    card_element.style('min-width: 80vw; width: 90vw; height: 90vh; max-width: none;')
                else:
                    card_element.style('min-width: 600px; width: auto; max-width: 800px; height: auto;')

    wit

