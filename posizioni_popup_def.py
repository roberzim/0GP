# posizioni_popup_def.py — JSON-only
from __future__ import annotations

from nicegui import ui
from pathlib import Path
import json, os
from typing import List, Optional, Callable

POSIZIONI_JSON = Path('lib_json/posizioni.json')


# --------------------- IO JSON (con scrittura atomica) ---------------------

def _read_posizioni_file() -> List[str]:
    if POSIZIONI_JSON.exists():
        try:
            data = json.loads(POSIZIONI_JSON.read_text(encoding='utf-8'))
            if isinstance(data, dict):
                lst = data.get('posizioni', [])
            elif isinstance(data, list):
                lst = data
            else:
                lst = []
            return [s for s in lst if isinstance(s, str) and s.strip()]
        except Exception:
            return []
    return []

def _write_posizioni_file(voci: List[str]) -> None:
    POSIZIONI_JSON.parent.mkdir(parents=True, exist_ok=True)
    # normalizza: strip, dedup, ordina
    clean = sorted({(s or '').strip() for s in voci if isinstance(s, str) and s.strip()})
    payload = {'posizioni': clean}
    tmp = POSIZIONI_JSON.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(tmp, POSIZIONI_JSON)  # atomico su stessa partizione


# --------------------- API interne ---------------------

def _carica_posizioni() -> List[str]:
    return _read_posizioni_file()

def _salva_posizioni(voci: List[str]) -> None:
    _write_posizioni_file(voci)


# --------------------- UI ---------------------

def mostra_popup_posizioni(on_update: Optional[Callable[[], None]] = None):
    voci = _carica_posizioni()

    dialog = ui.dialog()
    with dialog, ui.card().classes('w-full max-w-lg p-4'):
        ui.label('Gestione Posizioni').classes('text-lg font-bold mb-2')

        lista = ui.select(
            options=voci,
            value=(voci[0] if voci else None),
            with_input=True,
            multiple=False
        ).props('use-chips clearable').classes('w-full')

        nuovo_input = ui.input(label='Nuova posizione').classes('w-full')

        def refresh():
            # ricarica da file per semplicità
            nonlocal voci
            voci = _carica_posizioni()
            lista.set_options(voci)
            # se la voce selezionata non esiste più, pulisci la selezione
            if lista.value and lista.value not in voci:
                lista.value = None
            if on_update:
                try:
                    on_update()
                except Exception:
                    pass

        def aggiungi():
            voce = (nuovo_input.value or '').strip()
            if not voce:
                ui.notify('Inserisci una voce', type='warning'); return
            if voce in voci:
                ui.notify('Voce già presente', type='warning'); return
            voci.append(voce)
            _salva_posizioni(voci)
            nuovo_input.value = ''
            refresh()
            ui.notify('Posizione aggiunta', type='positive')

        def elimina():
            voce = (lista.value or '').strip()
            if not voce:
                ui.notify('Seleziona una voce', type='warning'); return
            if voce in voci:
                voci.remove(voce)
                _salva_posizioni(voci)
                refresh()
                ui.notify('Posizione eliminata', type='positive')

        def rinomina():
            voce = (lista.value or '').strip()
            nuova = (nuovo_input.value or '').strip()
            if not voce or not nuova:
                ui.notify('Seleziona una voce e inserisci il nuovo nome', type='warning'); return
            if nuova in voci and nuova != voce:
                ui.notify('Esiste già una voce con quel nome', type='warning'); return
            # modifica in-place senza riassegnare voci (evita scope/shadowing)
            try:
                idx = voci.index(voce)
            except ValueError:
                ui.notify('Voce non trovata', type='negative'); return
            voci[idx] = nuova
            _salva_posizioni(voci)
            nuovo_input.value = ''
            refresh()
            lista.value = nuova
            ui.notify('Posizione rinominata', type='positive')

        with ui.row().classes('gap-2 mt-2'):
            ui.button('Aggiungi', on_click=aggiungi).props('icon=add')
            ui.button('Rinomina', on_click=rinomina).props('icon=edit')
            ui.button('Elimina', on_click=elimina).props('icon=delete')
            ui.space()
            ui.button('Chiudi', on_click=lambda: (refresh(), dialog.close())).props('icon=close')

    dialog.open()


# --- Retro-compatibilità ---
# Alcuni moduli importano ancora `mostra_popup_modifica_posizioni`.
# Manteniamo un alias verso la nuova funzione.
def mostra_popup_modifica_posizioni(on_update: Optional[Callable[[], None]] = None):
    return mostra_popup_posizioni(on_update=on_update)

