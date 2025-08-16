"""
Gestione 'Scadenze e Attività' con NiceGUI (patched).
- Migliorie:
  * Parametro opzionale `on_change` per notificare modifiche al chiamante (dirty-flag/salvataggio).
  * Ricalcoli robusti e aggiornamento totali di sezione (durata e tariffe) con mini-dashboard.
  * Protezioni extra su update UI e gestione differenze di firma in gtil_def.
  * FIX: somma tariffe robusta per stringhe/float (no AttributeError su .replace).
"""

from __future__ import annotations
from typing import Dict, Any, Optional, Callable, Tuple
from datetime import datetime
from zoneinfo import ZoneInfo
from nicegui import ui
import inspect

# Integrazione Calendar/Email
import gtil_def as gtil

TZ = ZoneInfo('Europe/Rome')
DATE_FMT = '%d/%m/%Y %H.%M.%S'


def _parse_dt(value: str) -> datetime:
    """Parse dd/mm/YYYY HH.MM.SS in tz Europe/Rome."""
    dt = datetime.strptime((value or '').strip(), DATE_FMT)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=TZ)
    return dt


def _format_row_mail(row: Dict[str, Any], id_pratica: str) -> str:
    """Corpo email: una riga con tutti i campi principali."""
    campi = [
        f"ID pratica: {id_pratica}",
        f"Descrizione: {row.get('descrizione', '')}",
        f"Data inizio: {row.get('data_inizio', '')}",
        f"Data scadenza: {row.get('data_scadenza', '')}",
        f"Durata stimata (min): {row.get('durata_stimata', '')}",
        f"Reminder (min prima): {row.get('minuti_prima_allert', '')}",
        f"ID evento: {row.get('id_evento', '') or ''}",
    ]
    return '\n'.join(campi)


def _try_get_calendar_id() -> Optional[str]:
    """Compat: solo se gtil_def richiede calendar_id in elimina_evento(eventId, calendar_id)."""
    try:
        creds = gtil._get_credentials()                  # presenti in molti setup gtil_*
        cal = gtil._build_calendar_service(creds)
        return gtil._get_calendar_id_by_summary(cal, gtil.CALENDAR_SUMMARY)
    except Exception:
        return None


def _safe_float(x: Any) -> float:
    try:
        return float(x)
    except Exception:
        return 0.0


def _coerce_number(v: Any) -> float:
    """Accetta float/int/str con virgole/euro; altrimenti 0.0."""
    if isinstance(v, (int, float)):
        return float(v)
    try:
        s = (v or '').strip()
        if not s:
            return 0.0
        return float(s.replace('€', '').replace(' ', '').replace(',', '.'))
    except Exception:
        return 0.0


def _sum_totals(scadenze: list) -> Tuple[int, float, float]:
    """Ritorna (durata_stimata_tot_min, tariffa_stimata_tot, tariffa_effettiva_tot)."""
    dur = 0
    ts = 0.0
    te = 0.0
    for r in scadenze or []:
        try:
            dur += int(r.get('durata_stimata') or 0)
        except Exception:
            pass
        ts += _coerce_number(r.get('tariffa_stimata'))
        te += _coerce_number(r.get('tariffa_effettiva'))
    return dur, ts, te


def mostra_tab_attivita(pratica_data: Dict[str, Any], on_change: Optional[Callable[[], None]] = None) -> None:
    """Tab 'Attività' collegata a pratica_data."""
    pratica_data.setdefault('scadenze', [])
    id_pratica: str = pratica_data.get('id_pratica', '')

    def _call_on_change():
        try:
            if on_change:
                on_change()
        except Exception:
            pass

    ui.label('Scadenze e Attività').classes('text-lg font-bold mb-2')

    # contenitore verticale delle righe
    table_container = ui.column().classes('w-full gap-2')

    # dashboard totali
    totals_row = ui.row().classes('gap-4 items-center my-2')
    with totals_row:
        lbl_dur = ui.label('Durata stimata tot: 0 min').classes('text-sm text-gray-700')
        lbl_ts  = ui.label('Tariffa stimata tot: € 0,00').classes('text-sm text-gray-700')
        lbl_te  = ui.label('Tariffa effettiva tot: € 0,00').classes('text-sm text-gray-700')

    def _refresh_totals_and_export():
        dur, ts, te = _sum_totals(pratica_data.get('scadenze'))
        try:
            lbl_dur.text = f'Durata stimata tot: {dur} min'; lbl_dur.update()
            lbl_ts.text  = f'Tariffa stimata tot: € {ts:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.'); lbl_ts.update()
            lbl_te.text  = f'Tariffa effettiva tot: € {te:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.'); lbl_te.update()
        except Exception:
            pass
        # Esporta anche su pratica_data (se serve per reindex/lista)
        pratica_data['scadenze_totale_durata_stimata'] = dur
        pratica_data['scadenze_totale_tariffa_stimata'] = round(ts, 2)
        pratica_data['scadenze_totale_tariffa_effettiva'] = round(te, 2)

    def aggiungi_riga(row: Optional[Dict[str, Any]] = None, add_to_model: bool = True):
        """Crea una riga UI. Se add_to_model=True, aggiunge anche nel model pratica_data['scadenze']."""
        riga: Dict[str, Any] = {
            'descrizione': '',
            'data_inizio': '',
            'data_scadenza': '',
            'minuti_prima_allert': 30,
            'durata_stimata': 0,       # calcolata (minuti) = fine - inizio
            'durata_effettiva': None,  # inserimento manuale (minuti)
            'scadenza': False,         # checkbox
            'tariffa_oraria': 300.0,   # €/h modificabile
            'tariffa_stimata': 0.0,    # (tariffa_oraria/60)*durata_stimata
            'tariffa_effettiva': 0.0,  # (tariffa_oraria/60)*durata_effettiva
            'id_evento': '',
        }
        if row:
            riga.update(row)

        # Evita duplicazioni quando renderizziamo righe esistenti
        if add_to_model:
            pratica_data['scadenze'].append(riga)

        with table_container:
            with ui.row().classes('items-end gap-2') as riga_ui:
                in_descr = ui.input('Descrizione').classes('w-64').bind_value(riga, 'descrizione')
                in_start = ui.input('Data inizio (DD/MM/YYYY HH.MM.SS)').classes('w-64').bind_value(riga, 'data_inizio')
                in_due = ui.input('Data scadenza (DD/MM/YYYY HH.MM.SS)').classes('w-64').bind_value(riga, 'data_scadenza')
                in_min_alert = ui.number('minuti_prima_allert', min=0, max=40320, format='%d').classes('w-40').bind_value(riga, 'minuti_prima_allert')
                in_durata = ui.number('durata_stimata (min)', min=0, max=1440, format='%d').classes('w-40').bind_value(riga, 'durata_stimata')
                in_event = ui.input('id_evento').classes('w-64').bind_value(riga, 'id_evento'); in_event.props('readonly')

                # Campi aggiuntivi
                in_scad_chk = ui.checkbox('Scadenza').bind_value(riga, 'scadenza')
                in_durata.props('readonly')
                in_durata_eff = ui.number('durata_effettiva (min)', min=0, max=100000, format='%d').classes('w-44').bind_value(riga, 'durata_effettiva')
                in_tariffa_oraria = ui.number('tariffa_oraria (€/h)', min=0, max=100000, step=1).classes('w-44').bind_value(riga, 'tariffa_oraria')
                in_tariffa_stimata = ui.input('Tariffa stimata (€)').classes('w-48').bind_value(riga, 'tariffa_stimata'); in_tariffa_stimata.props('readonly')
                in_tariffa_effettiva = ui.input('Tariffa effettiva (€)').classes('w-48').bind_value(riga, 'tariffa_effettiva'); in_tariffa_effettiva.props('readonly')

                def _recalc_fields():
                    # Calcola durata_stimata = differenza (minuti) tra data_scadenza e data_inizio
                    try:
                        start = _parse_dt(str(riga.get('data_inizio', '') or ''))
                        end = _parse_dt(str(riga.get('data_scadenza', '') or ''))
                        delta_min = int((end - start).total_seconds() // 60)
                        if delta_min < 0:
                            delta_min = 0
                    except Exception:
                        delta_min = 0
                    riga['durata_stimata'] = delta_min
                    try:
                        in_durata.update()
                    except Exception:
                        pass

                    # Tariffe
                    to = _safe_float(riga.get('tariffa_oraria') or 300.0)

                    # Tariffa stimata da durata_stimata
                    tariffa_st = round((to / 60.0) * float(riga.get('durata_stimata') or 0), 2)
                    riga['tariffa_stimata'] = f"{tariffa_st:.2f}"
                    try:
                        in_tariffa_stimata.update()
                    except Exception:
                        pass

                    # Tariffa effettiva da durata_effettiva
                    de = _safe_float(riga.get('durata_effettiva') or 0)
                    tariffa_eff = round((to / 60.0) * de, 2)
                    riga['tariffa_effettiva'] = f"{tariffa_eff:.2f}"
                    try:
                        in_tariffa_effettiva.update()
                    except Exception:
                        pass

                    _refresh_totals_and_export()
                    _call_on_change()

                # Trigger ricalcolo
                in_start.on('blur', lambda e: _recalc_fields())
                in_due.on('blur', lambda e: _recalc_fields())
                in_durata_eff.on('blur', lambda e: _recalc_fields())
                in_tariffa_oraria.on('blur', lambda e: _recalc_fields())

                # Ricalcolo iniziale
                ui.timer(0.05, _recalc_fields, once=True)

                def salva_click():
                    _recalc_fields()  # aggiorna i campi calcolati prima del salvataggio
                    # Validazioni di base
                    if not str(riga.get('descrizione', '')).strip():
                        ui.notify('La descrizione è obbligatoria', type='warning'); return
                    try:
                        _ = _parse_dt(str(riga.get('data_inizio', '')))
                        due_at = _parse_dt(str(riga.get('data_scadenza', '')))
                    except Exception:
                        ui.notify(f"Formato data non valido. Usa {DATE_FMT}", type='negative'); return
                    try:
                        minuti = int(riga.get('minuti_prima_allert', 0))
                        durata = int(riga.get('durata_stimata', 0))
                    except Exception:
                        ui.notify('minuti_prima_allert deve essere un intero', type='negative'); return

                    # Titolo evento: "<id_pratica> - <descrizione>"
                    titolo = f"{id_pratica} - {riga['descrizione']}".strip(' -')
                    descr_evento = _format_row_mail(riga, id_pratica)

                    # Crea evento su Google Calendar con 2 reminder (popup + email)
                    try:
                        reminders = [
                            gtil.Reminder(method='popup', minutes=minuti),
                            gtil.Reminder(method='email', minutes=minuti),
                        ]
                        event_id = gtil.add_deadline(
                            title=titolo,
                            due_at=due_at,
                            duration_minutes=durata,  # durata_stimata
                            reminders=reminders,
                            description=descr_evento,
                        )
                    except Exception as e:
                        ui.notify(f'Errore creazione evento: {e}', type='negative'); return

                    # Invia email di conferma nuova scadenza
                    try:
                        gtil.send_message(
                            subject=f"Nuova scadenza: {titolo}",
                            body_text=descr_evento,
                        )
                    except Exception as e:
                        ui.notify(f'Evento creato ma email non inviata: {e}', type='warning')

                    # Aggiorna id_evento nella riga e UI
                    riga['id_evento'] = event_id
                    try:
                        in_event.update()
                    except Exception:
                        pass

                    # Aggiungi nuova riga vuota (questa va anche nel model)
                    aggiungi_riga(add_to_model=True)
                    _refresh_totals_and_export()
                    _call_on_change()
                    ui.notify('Scadenza salvata', type='positive')

                def elimina_click():
                    event_id = (str(riga.get('id_evento', ''))).strip()
                    # Prepara corpo email PRIMA di mutare i dati
                    descr_mail = _format_row_mail(riga, id_pratica)

                    # Elimina da Google Calendar se presente
                    if event_id:
                        try:
                            sig = inspect.signature(gtil.elimina_evento)
                            if len(sig.parameters) == 1:
                                gtil.elimina_evento(event_id)
                            else:
                                cal_id = _try_get_calendar_id()
                                if not cal_id:
                                    raise RuntimeError("Calendario 'Scadenze_TiL' non trovato")
                                gtil.elimina_evento(event_id, cal_id)
                        except Exception as e:
                            ui.notify(f'Errore cancellazione evento: {e}', type='negative')

                    # Email di cancellazione
                    try:
                        titolo = f"{id_pratica} - {riga.get('descrizione', '')}".strip(' -')
                        gtil.send_message(
                            subject=f"Cancellazione scadenza: {titolo}",
                            body_text=descr_mail + "\n\n(Scadenza cancellata)",
                        )
                    except Exception as e:
                        ui.notify(f'Email di cancellazione non inviata: {e}', type='warning')

                    # Se è la prima riga del model, svuota i campi invece di eliminare
                    if pratica_data['scadenze'] and pratica_data['scadenze'][0] is riga:
                        riga.update({
                            'descrizione': '',
                            'data_inizio': '',
                            'data_scadenza': '',
                            'minuti_prima_allert': 30,
                            'durata_stimata': 0,
                            'durata_effettiva': None,
                            'scadenza': False,
                            'tariffa_oraria': 300.0,
                            'tariffa_stimata': 0.0,
                            'tariffa_effettiva': 0.0,
                            'id_evento': '',
                        })
                        # aggiorna TUTTI i widget della riga
                        try:
                            in_descr.update(); in_start.update(); in_due.update(); in_min_alert.update(); in_durata.update()
                            in_durata_eff.update(); in_scad_chk.update(); in_tariffa_oraria.update()
                            in_tariffa_stimata.update(); in_tariffa_effettiva.update(); in_event.update()
                        except Exception:
                            pass
                        ui.notify('Prima riga svuotata', type='info')
                    else:
                        try:
                            pratica_data['scadenze'].remove(riga)
                        except ValueError:
                            pass
                        riga_ui.delete()
                        ui.notify('Riga eliminata', type='positive')

                    _refresh_totals_and_export()
                    _call_on_change()

                ui.button('Salva', on_click=salva_click).props('icon=save color=primary')
                ui.button('-', on_click=elimina_click).props('icon=remove_circle color=negative')

    # Render: righe esistenti (senza ri-aggiungerle al model) oppure riga vuota iniziale
    if pratica_data['scadenze']:
        for row in list(pratica_data['scadenze']):
            aggiungi_riga(row, add_to_model=False)  # evita duplicazioni
    else:
        aggiungi_riga(add_to_model=True)

    # inizializza totali
    _refresh_totals_and_export()
