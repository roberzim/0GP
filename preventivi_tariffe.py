# --- preventivi_tariffe.py (patched con micro-migliorie) ---
from __future__ import annotations
from typing import Dict, List, Callable, Optional
from nicegui import ui

# --- PDF export: import sicuro e wrapper -------------------------------------
try:
    import tabelle_ministeriali_safe as _tm
except Exception:
    try:
        import tabelle_ministeriali as _tm
    except Exception:
        _tm = None

def _pdf_available() -> bool:
    try:
        return bool(_tm and (getattr(_tm, "PDF_EXPORT_AVAILABLE", False) or hasattr(_tm, "genera_pdf_singolo")))
    except Exception:
        return False

PDF_OK = _pdf_available()

def export_pdf_singolo(dati, metadata, sezione):
    if _tm and PDF_OK and hasattr(_tm, "genera_pdf_singolo"):
        return _tm.genera_pdf_singolo(dati, metadata, sezione)
    ui.notify("Export PDF non disponibile (installare wkhtmltopdf/pdfkit).", type="warning")

def export_pdf_tutte(pratica_data, sezione):
    key = 'preventivi' if sezione == 'contenzioso' else 'preventivi_stragiudiziale'
    items = (pratica_data.get(key) or {})
    if not isinstance(items, dict) or not items:
        ui.notify('Nessuna tabella da esportare.', type='info'); return
    if not (_tm and PDF_OK and hasattr(_tm, "genera_pdf_singolo")):
        ui.notify("Export PDF non disponibile (installare wkhtmltopdf/pdfkit).", type="warning"); return
    ok = 0; fail = 0
    for _, obj in items.items():
        try:
            dati = (obj or {}).get('dati', {}) or {}
            md = (obj or {}).get('metadata', {}) or {}
            _tm.genera_pdf_singolo(dati, md, sezione)  # ogni chiamata attiva un download
            ok += 1
        except Exception:
            fail += 1
    ui.notify(f'Export {sezione}: {ok} file generati' + (f' — {fail} errori' if fail else ''), type=('positive' if ok else 'warning'))

def _on_upload(e, pratica_data, refresh_callback, sezione):
    if _tm and hasattr(_tm, "handle_upload"):
        return _tm.handle_upload(e, pratica_data, refresh_callback, sezione)
    ui.notify('Caricamento tabelle non disponibile (modulo tabelle_ministeriali assente).', type='warning')
# -----------------------------------------------------------------------------


def fmt(x: float) -> str:
    s = f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return s


# ---------- Helper parsing/somme ----------
def _parse_euro(v) -> float:
    if v is None:
        return 0.0
    s = str(v).strip()
    if not s:
        return 0.0
    s = s.replace('€', '').replace(' ', '')
    if ',' in s and '.' in s:
        s = s.replace('.', '').replace(',', '.')
    else:
        s = s.replace(',', '.')
    try:
        return float(s)
    except Exception:
        return 0.0

def _somma_tariffe(pratica_data: Dict, sezione: str) -> float:
    key = f"tariffe_{sezione}"
    totale = 0.0
    blocco = pratica_data.get(key, {}) or {}
    for _tipo, righe in (blocco.items() if isinstance(blocco, dict) else []):
        for r in righe or []:
            totale += _parse_euro((r or {}).get('tot'))
    return totale

def _somma_tabelle(pratica_data: Dict, sezione: str) -> float:
    key = 'preventivi' if sezione == 'contenzioso' else 'preventivi_stragiudiziale'
    totale = 0.0
    for _k, obj in ((pratica_data.get(key, {}) or {}).items() if isinstance(pratica_data.get(key, {}), dict) else []):
        dati = (obj or {}).get('dati', {}) or {}
        totale += _parse_euro(dati.get('totale_documento'))
    return totale
# ------------------------------------------------------


def gestisci_tab_preventivi(pratica_data: Dict, on_change: Optional[Callable[[], None]] = None) -> None:
    """Costruisce la scheda Preventivi/Tariffe.
    on_change: callback opzionale chiamata quando cambiano i totali (per dirty-flag/salvataggio).
    """
    tipi_tariffe = ['Base', 'Forfait', 'A Percentuale', 'A Risultato', 'Oraria', 'Abbonamento']

    # Etichette per i due totali di sezione (per poterli leggere fuori dalle colonne)
    totale_contenzioso = {'val': 0.0}
    totale_stragiud = {'val': 0.0}
    totale_generale = {'label': None}

    def _call_on_change():
        try:
            if on_change:
                on_change()
        except Exception:
            pass

    def update_totali_generale():
        tot = float(totale_contenzioso['val']) + float(totale_stragiud['val'])
        lbl = totale_generale['label']
        if lbl is not None:
            lbl.text = f"Totale Generale: € {fmt(tot)}"
            try:
                lbl.update()
            except Exception:
                pass
        # esporta anche dentro pratica_data
        pratica_data['totale_contenzioso'] = float(totale_contenzioso['val'])
        pratica_data['totale_stragiudiziale'] = float(totale_stragiud['val'])
        pratica_data['totale_generale'] = tot
        _call_on_change()

    with ui.column().classes('w-full h-full gap-4'):
        with ui.row().classes('w-full gap-4 no-wrap'):
            # Colonna contenzioso (sinistra)
            with ui.column().classes('w-1/2 p-4 border-r border-gray-200'):
                gestisci_sezione_tariffe(
                    pratica_data, 'contenzioso', tipi_tariffe,
                    totale_out=totale_contenzioso, on_update_totale=update_totali_generale
                )

            # Colonna stragiudiziale (destra)
            with ui.column().classes('w-1/2 p-4'):
                gestisci_sezione_tariffe(
                    pratica_data, 'stragiudiziale', tipi_tariffe,
                    totale_out=totale_stragiud, on_update_totale=update_totali_generale
                )

        ui.separator().classes('my-4')
        with ui.row().classes('w-full justify-between items-center bg-blue-50 p-2 rounded'):
            with ui.row().classes('items-center'):
                ui.icon('functions').classes('mr-1 text-blue-900')
                totale_generale['label'] = ui.label("Totale Generale: € 0,00").classes('text-xl font-bold text-blue-900')
            # Toolbar esportazione (se funzione disponibile)
            def _export_all(sezione: str):
                return export_pdf_tutte(pratica_data, sezione)

            with ui.row().classes('gap-2'):
                if PDF_OK:
                    ui.button('Esporta PDF Contenzioso', on_click=lambda: _export_all('contenzioso')).props('icon=picture_as_pdf')
                    ui.button('Esporta PDF Stragiudiziale', on_click=lambda: _export_all('stragiudiziale')).props('icon=picture_as_pdf')
                else:
                    ui.badge('PDF non disponibile').props('color=warning').classes('q-ml-sm')


        update_totali_generale()


def gestisci_sezione_tariffe(pratica_data: Dict, sezione: str, tipi_tariffe: list,
                             totale_out: dict | None = None,
                             on_update_totale: Callable[[], None] | None = None) -> None:
    titolo = 'Contenzioso' if sezione == 'contenzioso' else 'Attività Stragiudiziali'
    totale_label = ui.label('Totale: € 0,00').classes('text-lg font-bold text-right text-blue-900 w-full')

    def update_totale():
        tar = _somma_tariffe(pratica_data, sezione)
        tab = _somma_tabelle(pratica_data, sezione)
        tot = tar + tab
        totale_label.text = f"Totale {titolo}: € {fmt(tot)}   (Tariffe: € {fmt(tar)} — Tabelle: € {fmt(tab)})"
        try:
            totale_label.update()
        except Exception:
            pass
        if totale_out is not None:
            totale_out['val'] = tot
        if on_update_totale:
            on_update_totale()

    with ui.tabs().classes('w-full') as tabs:
        tariffe_tab = ui.tab('Tariffe')
        tabelle_tab = ui.tab('Tabelle Ministeriali')

    with ui.tab_panels(tabs, value=tariffe_tab).classes('w-full'):
        # ---- TARIFFE
        with ui.tab_panel(tariffe_tab):
            with ui.column().classes('w-full gap-4'):
                for tipo in tipi_tariffe:
                    TariffaManager(tipo, pratica_data, f'tariffe_{sezione}', on_change=update_totale).crea_interfaccia()
            ui.timer(0.05, update_totale, once=True)

        # ---- TABELLE
        with ui.tab_panel(tabelle_tab):
            tabella_container = ui.column().classes('w-full mt-4')

            def refresh_tabelle_e_totale():
                mostra_tabelle_sezione(pratica_data, tabella_container, sezione)
                update_totale()

            upload = ui.upload(
                on_upload=lambda e: _on_upload(e, pratica_data, refresh_tabelle_e_totale, sezione),
                auto_upload=True
            ).props('accept=.json').classes('hidden')

            with ui.row().classes('w-full justify-end gap-2 mt-2'):
                ui.button('Carica tabella ministeriale', on_click=lambda: upload.run_method('pickFiles'))                     .props('icon=upload color=positive')                     .classes('shadow-sm')

            refresh_tabelle_e_totale()

    ui.separator().classes('my-2')
    with ui.row().classes('w-full justify-end'):
        ui.icon('summarize').classes('mr-1 text-blue-900')


def mostra_tabelle_sezione(pratica_data: Dict, container: ui.column, sezione: str) -> None:
    container.clear()
    _tm.mostra_tabelle_ministeriali(pratica_data, container, lambda: mostra_tabelle_sezione(pratica_data, container, sezione), sezione) if (_tm and hasattr(_tm, 'mostra_tabelle_ministeriali')) else ui.label('Modulo tabelle ministeriali non disponibile').classes('text-gray-500 italic')


class TariffaManager:
    def __init__(self, tipo: str, pratica_data: Dict, categoria: str, on_change: Callable[[], None] | None = None):
        self.tipo = tipo
        self.pratica_data = pratica_data
        self.categoria = categoria  # es. 'tariffe_contenzioso'
        self.righe: List[Dict] = []
        self.on_change = on_change or (lambda: None)

    def _fmt_num(self, x: float) -> str:
        try:
            return fmt(float(x))
        except Exception:
            try:
                return f"{float(x):.2f}"
            except Exception:
                return "0,00"

    # --- ricalcoli ---
    def _ricalcola_tot_oraria(self, row: Dict) -> None:
        """Aggiorna 'tot' = tariffa_oraria/60 * minuti (se presenti)."""
        tariffa = _parse_euro(row.get('tariffa_oraria').value if row.get('tariffa_oraria') else 0)
        minuti = _parse_euro(row.get('tempo_stimato').value if row.get('tempo_stimato') else 0)
        if tariffa or minuti:
            val = (tariffa / 60.0) * minuti
            row['tot'].value = self._fmt_num(val)
            try:
                row['tot'].update()
            except Exception:
                pass

    def _ricalcola_tot_percentuale(self, row: Dict) -> None:
        """Aggiorna 'tot' = valore * percentuale / 100 per le tariffe A Percentuale."""
        valore = _parse_euro(row.get('valore').value if row.get('valore') else 0)
        perc = _parse_euro(row.get('percentuale').value if row.get('percentuale') else 0)
        if valore or perc:
            try:
                tot = (valore * perc) / 100.0
            except Exception:
                tot = 0.0
            row['tot'].value = self._fmt_num(tot)
            try:
                row['tot'].update()
            except Exception:
                pass
        # se presenti anche campi orari, calcola pure quello (rimane l'ultimo)
        tariffa = _parse_euro(row.get('tariffa_oraria').value if row.get('tariffa_oraria') else 0)
        minuti = _parse_euro(row.get('tempo_stimato').value if row.get('tempo_stimato') else 0)
        if tariffa or minuti:
            val = (tariffa / 60.0) * minuti
            row['tot'].value = self._fmt_num(val)
            try:
                row['tot'].update()
            except Exception:
                pass

    # --- UI ---
    def crea_interfaccia(self) -> None:
        """Crea la card per il tipo tariffa e popola le righe da pratica_data se presenti."""
        # leggi eventuali righe già salvate
        salvate: List[Dict] = (self.pratica_data.get(self.categoria, {}) or {}).get(self.tipo, []) or []

        with ui.card().classes('w-full shadow-sm'):
            with ui.card_section():
                # intestazione + prima riga
                with ui.row().classes('w-full items-center gap-2') as row_elem:
                    ui.label(self.tipo).classes('w-32 font-medium text-gray-700')
                    input_note = ui.input(label='Note').props('dense').classes('flex-grow')
                    # per tipo 'Oraria'
                    input_tariffa = input_minuti = None
                    # per tipo 'A Percentuale'
                    input_valore = input_percentuale = None

                    if self.tipo == 'Oraria':
                        input_tariffa = ui.input(label='Tariffa oraria (€ / h)').props('dense').classes('w-40')
                        input_minuti = ui.input(label='Tempo stimato (min)').props('dense').classes('w-40')
                        ui.label('Totale').classes('w-16 text-sm text-gray-600')
                        input_tot = ui.input(label='€').props('dense readonly').classes('w-32')  # ora readonly

                    elif self.tipo == 'A Percentuale':
                        input_valore = ui.input(label='Valore').props('dense').classes('w-36')
                        input_percentuale = ui.input(label='Percentuale (%)').props('dense').classes('w-36')
                        ui.label('Totale').classes('w-16 text-sm text-gray-600')
                        input_tot = ui.input(label='€').props('dense readonly').classes('w-32')  # readonly

                    else:
                        ui.label('Totale').classes('w-16 text-sm text-gray-600')
                        input_tot = ui.input(label='€').props('dense').classes('w-32')

                    ui.button('+', on_click=self.aggiungi_riga)                         .props('round dense color=positive')                         .classes('w-8 h-8')

                first_row = {'row': row_elem, 'note': input_note, 'tot': input_tot, 'is_first': True}
                if self.tipo == 'Oraria':
                    first_row['tariffa_oraria'] = input_tariffa
                    first_row['tempo_stimato'] = input_minuti
                if self.tipo == 'A Percentuale':
                    first_row['valore'] = input_valore
                    first_row['percentuale'] = input_percentuale
                self.righe.append(first_row)

                # attach eventi (dopo che first_row esiste)
                if self.tipo == 'Oraria':
                    input_tariffa.on('update:model-value', lambda e: (self._ricalcola_tot_oraria(first_row), self.aggiorna_dati(), self.on_change()))
                    input_minuti.on('update:model-value',  lambda e: (self._ricalcola_tot_oraria(first_row), self.aggiorna_dati(), self.on_change()))
                    # rimosso handler su input_tot (ora readonly)
                elif self.tipo == 'A Percentuale':
                    input_valore.on('update:model-value',      lambda e: (self._ricalcola_tot_percentuale(first_row), self.aggiorna_dati(), self.on_change()))
                    input_percentuale.on('update:model-value', lambda e: (self._ricalcola_tot_percentuale(first_row), self.aggiorna_dati(), self.on_change()))
                else:
                    input_tot.on('update:model-value', lambda e: (self.aggiorna_dati(), self.on_change()))

                # popolamento da dati salvati (se esistono), altrimenti default
                def _apply_values_to_row(row: Dict, data: Dict):
                    row['note'].value = data.get('note', '')
                    row['tot'].value = data.get('tot', '')
                    if 'tariffa_oraria' in row and row['tariffa_oraria']:
                        row['tariffa_oraria'].value = data.get('tariffa_oraria', '')
                    if 'tempo_stimato' in row and row['tempo_stimato']:
                        row['tempo_stimato'].value = data.get('tempo_stimato', '')
                    if 'valore' in row and row['valore']:
                        row['valore'].value = data.get('valore', '')
                    if 'percentuale' in row and row['percentuale']:
                        row['percentuale'].value = data.get('percentuale', '')
                    try:
                        row['note'].update(); row['tot'].update()
                    except Exception:
                        pass

                if salvate:
                    # prima riga dai dati[0]
                    _apply_values_to_row(first_row, salvate[0])
                    # righe successive
                    for data in salvate[1:]:
                        self.aggiungi_riga()
                        last = self.righe[-1]
                        _apply_values_to_row(last, data)
                    # ricalcoli iniziali ove necessario
                    if self.tipo == 'Oraria':
                        for r in self.righe:
                            self._ricalcola_tot_oraria(r)
                    if self.tipo == 'A Percentuale':
                        for r in self.righe:
                            self._ricalcola_tot_percentuale(r)
                else:
                    # ricalcolo iniziale se serve
                    if self.tipo == 'Oraria':
                        self._ricalcola_tot_oraria(first_row)
                    if self.tipo == 'A Percentuale':
                        self._ricalcola_tot_percentuale(first_row)

                self.aggiorna_dati()
                self.on_change()

    def aggiungi_riga(self) -> None:
        with ui.row().classes('w-full items-center gap-2 pl-10') as row_elem:
            ui.label(f"Aggiuntiva").classes('w-32 text-sm text-gray-500')
            input_note = ui.input(label='Note').props('dense').classes('flex-grow')
            # default campi
            input_tariffa = input_minuti = input_valore = input_percentuale = None

            if self.tipo == 'Oraria':
                input_tariffa = ui.input(label='Tariffa oraria (€ / h)').props('dense').classes('w-40')
                input_minuti = ui.input(label='Tempo stimato (min)').props('dense').classes('w-40')
                ui.label('Totale').classes('w-16 text-sm text-gray-500')
                input_tot = ui.input(label='€').props('dense readonly').classes('w-32')  # ora readonly
            elif self.tipo == 'A Percentuale':
                input_valore = ui.input(label='Valore').props('dense').classes('w-36')
                input_percentuale = ui.input(label='Percentuale (%)').props('dense').classes('w-36')
                ui.label('Totale').classes('w-16 text-sm text-gray-500')
                input_tot = ui.input(label='€').props('dense readonly').classes('w-32')
            else:
                ui.label('Totale').classes('w-16 text-sm text-gray-500')
                input_tot = ui.input(label='€').props('dense').classes('w-32')

            # placeholder dict per catturare 'riga' nelle lambda
            riga = {'row': row_elem, 'note': input_note, 'tot': input_tot, 'is_first': False}
            if self.tipo == 'Oraria':
                riga['tariffa_oraria'] = input_tariffa
                riga['tempo_stimato'] = input_minuti
            if self.tipo == 'A Percentuale':
                riga['valore'] = input_valore
                riga['percentuale'] = input_percentuale

            # attach eventi (dopo dizionario creato)
            input_note.on('update:model-value', lambda e: (self.aggiorna_dati(), self.on_change()))
            if self.tipo == 'Oraria':
                input_tariffa.on('update:model-value', lambda e, r=riga: (self._ricalcola_tot_oraria(r), self.aggiorna_dati(), self.on_change()))
                input_minuti.on('update:model-value',  lambda e, r=riga: (self._ricalcola_tot_oraria(r), self.aggiorna_dati(), self.on_change()))
                # rimosso handler su input_tot (ora readonly)
            elif self.tipo == 'A Percentuale':
                input_valore.on('update:model-value',      lambda e, r=riga: (self._ricalcola_tot_percentuale(r), self.aggiorna_dati(), self.on_change()))
                input_percentuale.on('update:model-value', lambda e, r=riga: (self._ricalcola_tot_percentuale(r), self.aggiorna_dati(), self.on_change()))
            else:
                input_tot.on('update:model-value', lambda e: (self.aggiorna_dati(), self.on_change()))

            ui.button('-', on_click=lambda r=riga: self.rimuovi_riga(r))                 .props('round dense color=negative')                 .classes('w-8 h-8')

            self.righe.append(riga)

        # ricalcolo immediato
        if self.tipo == 'Oraria':
            self._ricalcola_tot_oraria(riga)
        if self.tipo == 'A Percentuale':
            self._ricalcola_tot_percentuale(riga)
        self.aggiorna_dati()
        self.on_change()

    def rimuovi_riga(self, riga: Dict) -> None:
        try:
            if riga.get('row') is not None:
                riga['row'].delete()
        except Exception:
            pass
        self.righe = [r for r in self.righe if r != riga]
        self.aggiorna_dati()
        self.on_change()

    def aggiorna_dati(self) -> None:
        if self.categoria not in self.pratica_data:
            self.pratica_data[self.categoria] = {}
        righe_serializzate = []
        for r in self.righe:
            row_dict = {
                'note': r['note'].value,
                'tot': r['tot'].value,
            }
            if self.tipo == 'Oraria':
                row_dict['tariffa_oraria'] = r.get('tariffa_oraria').value if r.get('tariffa_oraria') else ''
                row_dict['tempo_stimato'] = r.get('tempo_stimato').value if r.get('tempo_stimato') else ''
            if self.tipo == 'A Percentuale':
                row_dict['valore'] = r.get('valore').value if r.get('valore') else ''
                row_dict['percentuale'] = r.get('percentuale').value if r.get('percentuale') else ''
            righe_serializzate.append(row_dict)

        self.pratica_data[self.categoria][self.tipo] = righe_serializzate
