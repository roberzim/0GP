# calcola_ore_popup_def.py
from nicegui import ui
from utils import stile_popup, crea_pulsanti_controllo  # stile e pulsanti coerenti con gli altri popup


def mostra_popup_calcola_ore():
    """Popup unico con:
    1) Minuti → Ore/Giorni/Settimane
    2) Ore+Minuti → Minuti totali
    """
    stile_popup()  # CSS comune

    dialog = ui.dialog().classes('w-full')
    with dialog, ui.card().classes('popup-card') as card:
        ui.label('Calcolatrice Tempo').classes('popup-header')

        with ui.column().classes('gap-4'):
            # --- Sezione: Minuti → Ore/Giorni/Settimane ---
            ui.separator().classes('my-2')
            ui.label('Minuti → Ore / Giorni / Settimane').classes('text-sm text-gray-500')
            with ui.row().classes('items-end gap-3'):
                in_min = ui.number('Minuti', min=0, format='%d').classes('w-40')
                out_ore = ui.input('Ore').props('readonly').classes('w-40')
                out_giorni = ui.input('Giorni').props('readonly').classes('w-40')
                out_settimane = ui.input('Settimane').props('readonly').classes('w-40')

            with ui.row().classes('gap-2'):
                def calcola_da_minuti():
                    try:
                        m = int(in_min.value or 0)
                    except Exception:
                        m = 0
                    ore = m / 60
                    giorni = m / (60 * 24)
                    settimane = m / (60 * 24 * 7)
                    out_ore.value = f'{ore:.2f}'
                    out_giorni.value = f'{giorni:.3f}'
                    out_settimane.value = f'{settimane:.4f}'

                def copia_risultati():
                    ui.clipboard.write(
                        f"Minuti: {in_min.value or 0}\n"
                        f"Ore: {out_ore.value or ''}\n"
                        f"Giorni: {out_giorni.value or ''}\n"
                        f"Settimane: {out_settimane.value or ''}"
                    )
                    ui.notify('Risultati copiati', type='positive')

                ui.button('Calcola', icon='functions', on_click=calcola_da_minuti).classes('popup-button')
                ui.button('Copia risultati', icon='content_copy', on_click=copia_risultati).classes('popup-button')

            # --- Sezione: Ore + Minuti → Minuti totali ---
            ui.separator().classes('my-2')
            ui.label('Ore + Minuti → Minuti totali').classes('text-sm text-gray-500')
            with ui.row().classes('items-end gap-3'):
                in_ore = ui.number('Ore', min=0, format='%d').classes('w-32')
                in_minuti_extra = ui.number('Minuti', min=0, max=59, format='%d').classes('w-32')
                out_minuti_tot = ui.input('Totale minuti').props('readonly').classes('w-40')

            with ui.row().classes('gap-2'):
                def calcola_minuti_tot():
                    try:
                        ore_val = int(in_ore.value or 0)
                    except Exception:
                        ore_val = 0
                    try:
                        min_val = int(in_minuti_extra.value or 0)
                    except Exception:
                        min_val = 0
                    out_minuti_tot.value = str(ore_val * 60 + min_val)

                ui.button('Calcola minuti totali', icon='functions', on_click=calcola_minuti_tot).classes('popup-button')

        # Pulsanti di controllo (chiudi, ecc.) coerenti con gli altri popup
        crea_pulsanti_controllo(dialog, card)

    dialog.open()

