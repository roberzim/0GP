from nicegui import ui
import json
import uuid
from typing import Dict, List, Callable, Optional
from datetime import datetime
import html
import os
import shutil

# --- import sicuro di pdfkit -------------------------------------------------
try:
    import pdfkit  # type: ignore
    _PDFKIT_AVAILABLE = True
except Exception:  # ImportError o altro
    pdfkit = None  # type: ignore
    _PDFKIT_AVAILABLE = False

# Stile CSS per il PDF
PDF_STYLE = """
    <style>
        body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
        h1 { color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 5px; }
        h2 { color: #2980b9; margin-top: 20px; }
        h3 { color: #16a085; }
        table { width: 100%; border-collapse: collapse; margin: 15px 0; }
        th { background-color: #3498db; color: white; text-align: left; padding: 8px; }
        td { padding: 8px; border-bottom: 1px solid #ddd; }
        tr:nth-child(even) { background-color: #f2f2f2; }
        .header { display: flex; justify-content: space-between; margin-bottom: 20px; }
        .logo { max-width: 150px; }
        .metadata { background-color: #f8f9fa; padding: 15px; border-radius: 5px; margin-bottom: 20px; }
        .total { font-size: 1.2em; font-weight: bold; text-align: right; margin-top: 20px; }
        .footer { margin-top: 30px; padding-top: 10px; border-top: 1px solid #eee; text-align: center; font-size: 0.8em; }
        .break-after { page-break-after: always; }
    </style>
"""

# ---------- Helpers ----------

def fmt_eur(x: float | int) -> str:
    try:
        s = f"{float(x):,.2f}"
    except Exception:
        return "0,00"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")

def _safe_int(x) -> int:
    try:
        return int(x)
    except Exception:
        return 0

def _wkhtmltopdf_path() -> Optional[str]:
    candidates = [
        shutil.which("wkhtmltopdf"),
        "/usr/bin/wkhtmltopdf",
        "/usr/local/bin/wkhtmltopdf",
        r"C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe",
        r"C:\Program Files (x86)\wkhtmltopdf\bin\wkhtmltopdf.exe",
    ]
    for c in candidates:
        if c and os.path.exists(c):
            return c
    return None

def _wkhtmltopdf_config():
    """Prova ad auto-trovare wkhtmltopdf; se non disponibile, ritorna None."""
    if not _PDFKIT_AVAILABLE:
        return None
    path = _wkhtmltopdf_path()
    if path and pdfkit:  # type: ignore
        return pdfkit.configuration(wkhtmltopdf=path)  # type: ignore
    return None

def _render_html_tabella(dati: Dict, metadata: Dict, sezione: str) -> str:
    """Ritorna un frammento HTML completo per UNA tabella."""
    # Intestazione con data corrente
    data_corrente = datetime.now().strftime("%d/%m/%Y %H:%M")
    md_data = html.escape(str(metadata.get('data', 'N/D')))
    md_ambito = html.escape(str(metadata.get('ambito', 'N/D')))
    md_scagl = html.escape(str(metadata.get('scaglione', 'N/D')))

    parts: List[str] = []
    parts.append(f"""
        <div class="header">
            <div>
                <h1>Tabella Ministeriale</h1>
                <p>{html.escape(sezione.capitalize())}</p>
            </div>
            <div>
                <p>Generato il: {data_corrente}</p>
            </div>
        </div>

        <div class="metadata">
            <h2>Metadati</h2>
            <table>
                <tr><th>Data</th><td>{md_data}</td></tr>
                <tr><th>Ambito</th><td>{md_ambito}</td></tr>
                <tr><th>Scaglione</th><td>{md_scagl}</td></tr>
            </table>
        </div>
    """)

    # Fasi
    fasi = dati.get('fasi', {}) or {}
    if fasi:
        rows = []
        for nome, info in fasi.items():
            nome = html.escape(str(nome))
            valore_medio = fmt_eur(info.get('valore_medio', 0))
            aumento = float(info.get('aumento', 0) or 0)
            riduzione = float(info.get('riduzione', 0) or 0)
            if aumento > 0:
                variazione = f"+{aumento:.0f}%"
            elif riduzione > 0:
                variazione = f"-{riduzione:.0f}%"
            else:
                variazione = ""
            compenso = fmt_eur(info.get('compenso', 0))
            rows.append(f"""
                <tr>
                    <td>{nome}</td>
                    <td style="text-align: right;">€ {valore_medio}</td>
                    <td style="text-align: center;">{variazione}</td>
                    <td style="text-align: right;">€ {compenso}</td>
                </tr>
            """)
        parts.append("""
            <h2>Fasi Processuali</h2>
            <table>
                <thead>
                    <tr>
                        <th>Fase</th>
                        <th>Valore Medio</th>
                        <th>Variazione</th>
                        <th>Compenso</th>
                    </tr>
                </thead>
                <tbody>
        """)
        parts.extend(rows)
        parts.append("</tbody></table>")

    # Prospetto
    prospetto = dati.get('prospetto', {}) or {}
    if prospetto:
        parts.append("""
            <h2>Prospetto Finale</h2>
            <table>
                <thead>
                    <tr>
                        <th>Descrizione</th>
                        <th>Importo</th>
                    </tr>
                </thead>
                <tbody>
        """)
        for descrizione, importo in prospetto.items():
            parts.append(f"""
                <tr>
                    <td>{html.escape(str(descrizione))}</td>
                    <td style="text-align: right;">€ {fmt_eur(importo)}</td>
                </tr>
            """)
        parts.append("</tbody></table>")

    totale = dati.get('totale_documento', 0) or 0
    parts.append(f"""
        <div class="total">
            Totale documento: € {fmt_eur(totale)}
        </div>
    """)
    return "\n".join(parts)

# Disponibilità export PDF
PDF_EXPORT_AVAILABLE: bool = bool(_PDFKIT_AVAILABLE and _wkhtmltopdf_path())

def _pdf_from_html(html_str: str, filename: str) -> None:
    if not PDF_EXPORT_AVAILABLE or not _PDFKIT_AVAILABLE or not pdfkit:  # type: ignore
        ui.notify('Export PDF non disponibile (pdfkit/wkhtmltopdf assenti).', type='warning')
        return
    try:
        config = _wkhtmltopdf_config()
        if config is None:
            ui.notify('wkhtmltopdf non trovato. Installa il pacchetto di sistema o imposta il path.', type='negative')
            return
        pdf_bytes = pdfkit.from_string(html_str, False, options={  # type: ignore
            'encoding': 'UTF-8',
            'margin-top': '15mm',
            'margin-right': '15mm',
            'margin-bottom': '15mm',
            'margin-left': '15mm',
        }, configuration=config)
        ui.download(pdf_bytes, filename)
        ui.notify('PDF generato con successo!', type='positive')
    except Exception as e:
        ui.notify(f"Errore durante la generazione del PDF: {str(e)}", type='negative')

# ---------- UI principale ----------

def mostra_tabelle_ministeriali(pratica_data: Dict, container: ui.column, refresh_callback: Callable, sezione: str = 'contenzioso') -> None:
    key = 'preventivi' if sezione == 'contenzioso' else 'preventivi_stragiudiziale'
    container.clear()

    blocco = pratica_data.get(key) or {}
    if not blocco:
        ui.label("Nessuna tabella ministeriale caricata").classes('text-gray-500 italic')
        return

    # Barra azioni globali
    with container:
        with ui.row().classes('w-full justify-end mb-2'):
            if PDF_EXPORT_AVAILABLE:
                ui.button('Esporta tutte in PDF', icon='picture_as_pdf',
                          on_click=lambda: genera_pdf_tutte(pratica_data, sezione)) \
                  .props('color=negative flat').classes('shadow-sm')
            else:
                # Mostra un suggerimento non intrusivo
                ui.tooltip('Installa wkhtmltopdf per abilitare l\'export PDF')
                ui.badge('PDF non disponibile').props('color=warning').classes('q-ml-sm')

    # render ordinato per numero
    for numero, preventivo_obj in sorted(blocco.items(), key=lambda x: _safe_int(x[0])):
        dati = preventivo_obj.get('dati', {}) or {}
        metadata = preventivo_obj.get('metadata', {}) or {}

        with container:
            with ui.card().classes('w-full mb-6 shadow-lg') as preventivo_container:
                with ui.card_section().classes('bg-blue-50'):
                    ui.label(f"Tabella Ministeriale #{numero} ({sezione.capitalize()})").classes('text-lg font-bold text-blue-800')
                
                # (campi metadata / tabelle come nel tuo codice originale)...
                fasi = dati.get('fasi', {})
                if fasi:
                    with ui.card_section():
                        ui.label('Fasi processuali').classes('text-md font-bold mt-2 mb-2 text-blue-700')
                        rows_fasi = []
                        for nome, info in fasi.items():
                            if float(info.get('aumento', 0) or 0) > 0:
                                variazione = f"+{info['aumento']}%"
                            elif float(info.get('riduzione', 0) or 0) > 0:
                                variazione = f"-{info['riduzione']}%"
                            else:
                                variazione = ''
                            rows_fasi.append({
                                'fase': nome,
                                'valore_medio': f"€ {fmt_eur(info.get('valore_medio', 0))}",
                                'variazione': variazione,
                                'compenso': f"€ {fmt_eur(info.get('compenso', 0))}",
                            })
                        columns_fasi = [
                            {'name': 'fase', 'label': 'Fase', 'field': 'fase', 'align': 'left', 'sortable': True},
                            {'name': 'valore_medio', 'label': 'Valore Medio', 'field': 'valore_medio', 'align': 'right'},
                            {'name': 'variazione', 'label': 'Variazione', 'field': 'variazione', 'align': 'center'},
                            {'name': 'compenso', 'label': 'Compenso (€)', 'field': 'compenso', 'align': 'right'},
                        ]
                        ui.table(columns=columns_fasi, rows=rows_fasi, row_key='fase').classes('w-full').props('dense flat bordered')

                prospetto = dati.get('prospetto', {})
                if prospetto:
                    with ui.card_section():
                        ui.label('Prospetto Finale').classes('text-md font-bold mt-2 mb-2 text-blue-700')
                        rows = [{'descrizione': k, 'importo': f"€ {fmt_eur(v)}"} for k, v in prospetto.items()]
                        columns = [
                            {'name': 'descrizione', 'label': 'Descrizione', 'field': 'descrizione', 'align': 'left', 'sortable': True},
                            {'name': 'importo', 'label': 'Importo (€)', 'field': 'importo', 'align': 'right'}
                        ]
                        ui.table(columns=columns, rows=rows, row_key='descrizione').classes('w-full').props('dense flat bordered')

                totale = dati.get('totale_documento', 0) or 0
                if totale:
                    with ui.card_section().classes('bg-blue-50'):
                        ui.label(f"Totale documento: € {fmt_eur(totale)}").classes('text-lg font-bold text-right text-blue-800')

                with ui.card_actions().classes('justify-end'):
                    if PDF_EXPORT_AVAILABLE:
                        ui.button(icon='picture_as_pdf', on_click=lambda d=dati, m=metadata: genera_pdf_singolo(d, m, sezione))\
                            .props('flat color=negative').tooltip('Esporta in PDF')
                    ui.button(icon='delete', on_click=lambda n=numero, s=sezione: elimina_tabella(pratica_data, n, refresh_callback, s))\
                        .props('flat color=negative').tooltip('Elimina tabella')

def elimina_tabella(pratica_data: Dict, numero: int, refresh_callback: Callable, sezione: str = 'contenzioso') -> None:
    key = 'preventivi' if sezione == 'contenzioso' else 'preventivi_stragiudiziale'
    if numero in (pratica_data.get(key) or {}):
        del pratica_data[key][numero]
        ui.notify(f"Tabella #{numero} eliminata", type='positive')
        refresh_callback()

def carica_preventivo_json(content_text: str, pratica_data: Dict, sezione: str = 'contenzioso') -> None:
    key = 'preventivi' if sezione == 'contenzioso' else 'preventivi_stragiudiziale'
    blocco = pratica_data.setdefault(key, {})

    data = json.loads(content_text)

    # numero progressivo robusto
    esistenti = [ _safe_int(k) for k in (blocco.keys() if isinstance(blocco, dict) else []) ]
    numero = (max(esistenti) + 1) if esistenti else 1

    preventivo = {
        'id': str(uuid.uuid4()),
        'numero': numero,
        'dati': {
            'fasi': {},
            'prospetto': {},
            'totale_documento': round(float(data.get('totaleDocumento', 0) or 0), 2),
        },
        'metadata': data.get('metadata', {}) or {},
    }

    for fase in data.get('fasiProcessuali', []):
        try:
            if fase.get('selezionata') and float(fase.get('compensoParziale', 0) or 0) > 0:
                nome = (fase.get('nome') or '').strip()
                preventivo['dati']['fasi'][nome] = {
                    'compenso': round(float(fase.get('compensoParziale', 0) or 0), 2),
                    'aumento': float(fase.get('aumentoPercentuale', 0) or 0),
                    'riduzione': float(fase.get('riduzionePercentuale', 0) or 0),
                    'valore_medio': float(fase.get('valoreMedio', 0) or 0),
                }
        except Exception:
            # ignora righe malformate
            continue

    for voce in data.get('prospettoFinale', []):
        descrizione = (voce.get('descrizione') or '').strip()
        try:
            preventivo['dati']['prospetto'][descrizione] = round(float(voce.get('importo', 0) or 0), 2)
        except Exception:
            preventivo['dati']['prospetto'][descrizione] = 0.0

    blocco[numero] = preventivo

async def handle_upload(e, pratica_data: Dict, refresh_callback: Callable, sezione: str = 'contenzioso') -> None:
    try:
        content_text = e.content.read().decode('utf-8')
        carica_preventivo_json(content_text, pratica_data, sezione)
        ui.notify('Dati JSON caricati con successo', type='positive')
        refresh_callback()
    except json.JSONDecodeError:
        ui.notify("Errore: Il file non è un JSON valido", type='negative')
    except Exception as ex:
        ui.notify(f"Errore durante il caricamento: {str(ex)}", type='negative')

def genera_pdf_singolo(dati: Dict, metadata: Dict, sezione: str) -> None:
    # Documento con UNA tabella
    html_str = f"""
    <html>
        <head>
            <meta charset='UTF-8'>
            <title>Tabella Ministeriale - {html.escape(sezione.capitalize())}</title>
            {PDF_STYLE}
        </head>
        <body>
            {_render_html_tabella(dati, metadata, sezione)}
            <div class="footer">
                Documento generato automaticamente - Sistema di gestione preventivi
            </div>
        </body>
    </html>
    """
    nome_file = f"tabella_ministeriale_{sezione}_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
    _pdf_from_html(html_str, nome_file)

def genera_pdf_tutte(pratica_data: Dict, sezione: str = 'contenzioso') -> None:
    """Un unico PDF con TUTTE le tabelle della sezione, paginate."""
    key = 'preventivi' if sezione == 'contenzioso' else 'preventivi_stragiudiziale'
    blocco = pratica_data.get(key) or {}
    if not blocco:
        ui.notify('Nessuna tabella da esportare', type='warning')
        return

    parts: List[str] = [f"<html><head><meta charset='UTF-8'>{PDF_STYLE}</head><body>"]
    ordered = sorted(blocco.items(), key=lambda x: _safe_int(x[0]))
    last = len(ordered) - 1
    for i, (_, preventivo_obj) in enumerate(ordered):
        dati = preventivo_obj.get('dati', {}) or {}
        metadata = preventivo_obj.get('metadata', {}) or {}
        parts.append(_render_html_tabella(dati, metadata, sezione))
        if i != last:
            parts.append('<div class="break-after"></div>')
    parts.append("""
        <div class="footer">
            Documento generato automaticamente - Sistema di gestione preventivi
        </div></body></html>
    """)
    html_str = "\n".join(parts)
    nome_file = f"tabelle_ministeriali_{sezione}_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
    _pdf_from_html(html_str, nome_file)
