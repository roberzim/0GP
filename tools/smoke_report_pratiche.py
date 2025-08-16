# tools/smoke_report_pratiche.py
# Esegue gli smoke test (no-collision, overwrite, next-id) e genera un report HTML con i risultati.
# Auto-fix import path e apertura automatica del report nel browser.

import subprocess, sys, os, time, html, re, webbrowser
from pathlib import Path

# --- Fix import e working directory ---
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.chdir(str(ROOT))

TOOLS = ROOT / "tools"
REPORTS_DIR = ROOT / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

SMOKE = TOOLS / "smoke_suite_pratiche.py"
if not SMOKE.exists():
    print("ERRORE: tools/smoke_suite_pratiche.py non trovato. Crealo prima di lanciare questo script.")
    sys.exit(1)

SCENARIOS = [
    ("no-collision", "Nessuna collisione (flusso normale)"),
    ("overwrite", "Collisione: sovrascrive stesso ID_pratica"),
    ("next-id", "Collisione: usa ID_pratica successivo"),
]

def run_scenario(mode: str):
    cmd = [sys.executable, str(SMOKE), "--mode", mode]
    p = subprocess.run(cmd, cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    out = p.stdout
    # Estrazione info
    id_line = ""
    created_line = ""
    for line in out.splitlines():
        if line.startswith(f"[{mode}] ID:") and not id_line:
            id_line = line.strip()
        if line.startswith("File creati:") and not created_line:
            created_line = line.strip()

    m = re.search(r"ID:\s*([0-9]+/[0-9]+)\s+backup:\s*(True|False)\s+timestamped:\s*(True|False)", id_line)
    id_str = m.group(1) if m else "n/d"
    backup_ok = (m.group(2) == "True") if m else False
    ts_ok = (m.group(3) == "True") if m else False

    created_paths = []
    m2 = re.search(r"File creati:\s*(.+)$", created_line)
    if m2:
        parts = m2.group(1).split()
        created_paths = parts

    return {
        "mode": mode,
        "stdout": out,
        "id": id_str,
        "backup_ok": backup_ok,
        "timestamped_ok": ts_ok,
        "paths": created_paths,
        "returncode": p.returncode,
    }

def html_row(res):
    safe_log = html.escape(res["stdout"][-4000:])  # tail log (max 4000 chars)
    links = []
    for p in res["paths"]:
        rel = p.lstrip("./")
        links.append(f'<a href="{html.escape(rel)}" target="_blank">{html.escape(rel)}</a>')
    links_html = "<br/>".join(links) if links else "—"

    return f"""
    <tr>
      <td><code>{html.escape(res['mode'])}</code></td>
      <td>{html.escape(res['id'])}</td>
      <td class="center {'ok' if res['backup_ok'] else 'ko'}">{'OK' if res['backup_ok'] else 'NO'}</td>
      <td class="center {'ok' if res['timestamped_ok'] else 'ko'}">{'OK' if res['timestamped_ok'] else 'NO'}</td>
      <td>{links_html}</td>
      <td><details><summary>log</summary><pre>{safe_log}</pre></details></td>
    </tr>
    """

def main():
    ts = time.strftime("%Y%m%d_%H%M%S")
    results = [run_scenario(m) for m, _ in SCENARIOS]

    rows = "\n".join(html_row(r) for r in results)
    doc = f"""
    <!doctype html>
    <html lang="it">
    <head>
      <meta charset="utf-8"/>
      <meta name="viewport" content="width=device-width, initial-scale=1"/>
      <title>Smoke Report Pratiche — {ts}</title>
      <style>
        body {{ font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; margin: 24px; }}
        h1 {{ margin-top: 0; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th, td {{ border: 1px solid #e5e7eb; padding: 8px 10px; vertical-align: top; }}
        th {{ background: #f8fafc; text-align: left; }}
        td.center {{ text-align: center; white-space: nowrap; }}
        code {{ background: #f1f5f9; padding: 2px 4px; border-radius: 4px; }}
        .ok {{ color: #166534; font-weight: 600; }}
        .ko {{ color: #b91c1c; font-weight: 600; }}
        details > summary {{ cursor: pointer; }}
        pre {{ white-space: pre-wrap; word-break: break-word; background:#0b1021; color:#e2e8f0; padding:10px; border-radius:6px; }}
      </style>
    </head>
    <body>
      <h1>Smoke Report Pratiche</h1>
      <p>Data: {time.strftime("%d/%m/%Y %H:%M:%S")}</p>
      <table>
        <thead>
          <tr>
            <th>Scenario</th>
            <th>ID</th>
            <th>Backup</th>
            <th>Timestamped</th>
            <th>File creati</th>
            <th>Output</th>
          </tr>
        </thead>
        <tbody>
          {rows}
        </tbody>
      </table>
      <p style="margin-top:24px;color:#64748b">Generato da <code>tools/smoke_report_pratiche.py</code>.</p>
    </body>
    </html>
    """

    out = REPORTS_DIR / f"smoke_report_{ts}.html"
    out.write_text(doc, encoding="utf-8")
    print("Report HTML:", out)

    # Prova ad aprire automaticamente nel browser
    try:
        webbrowser.open_new_tab(out.resolve().as_uri())
    except Exception:
        # Fallback per OS
        try:
            if os.name == "nt":
                os.startfile(str(out))  # type: ignore
            elif os.name == "posix":
                os.system(f'xdg-open "{out}" >/dev/null 2>&1') or os.system(f'open "{out}" >/dev/null 2>&1')
        except Exception:
            pass

if __name__ == "__main__":
    main()
