#!/usr/bin/env python3
from repo import write_pratica
# LEGACY-CLEANUP: sostituito save_* con write_pratica; valutare dual_save(...) dopo il salvataggio canonico.
"""
PySide6 skeleton UI for “Gestione Pratiche”.

Features (MVP):
- Left: practices list from SQLite index (if available) or filesystem scan fallback.
- Right: details panel bound to JSON of selected practice + raw JSON viewer.
- Actions: New, Open, Save, Reindex, Refresh, Quit.
- Currency dropdown fed by CurrencyRegistry.allowed() if available, else fallback.
- Command-line options for paths.

Integrations to wire later (placeholders provided):
- Dual-save policy (user dir + app dir) in save_json_dual().
- Reindex via service.reindex_all().
- Validation via Pydantic in validate_json().

Run:
  python app_pyside6.py --db indice.sqlite --roots /path/archivio1 /path/archivio2

Requires: PySide6, (optional) sqlite3, pydantic (optional)
"""
from __future__ import annotations

import json
import os
import sys
import argparse
import sqlite3
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import (QAbstractTableModel, QModelIndex, QObject, Qt,
                            QSortFilterProxyModel, Signal)
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QFileDialog, QFormLayout, QGridLayout,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox,
    QPushButton, QPlainTextEdit, QSizePolicy, QSplitter, QStyle, QTableView,
    QToolBar, QVBoxLayout, QWidget
)

# ----------------------- Helpers & Placeholders ----------------------- #

def debug(msg: str):
    # Simple console logger
    print(f"[UI] {datetime.now().isoformat(timespec='seconds')} - {msg}")

class CurrencyRegistry:
    """Adapter that tries to import project registry, else uses fallback."""
    @staticmethod
    def allowed() -> List[str]:
        # Try import from project if available
        try:
            from currency_registry import CurrencyRegistry as CR  # type: ignore
            return list(CR.allowed())
        except Exception:
            # Fallback: try read valute.json or valute_full.json in CWD
            for fname in ("valute.json", "valute_full.json"):
                p = Path(fname)
                if p.exists():
                    try:
                        data = json.loads(p.read_text(encoding="utf-8"))
                        if isinstance(data, dict) and "codes" in data:
                            return list(data["codes"])  # custom format
                        if isinstance(data, list):
                            # expect a list of currency codes or objects
                            codes = []
                            for item in data:
                                if isinstance(item, str):
                                    codes.append(item)
                                elif isinstance(item, dict) and "code" in item:
                                    codes.append(item["code"])
                            if codes:
                                return codes
                    except Exception:
                        pass
            # Hardcoded minimal set
            return ["EUR", "USD", "GBP", "CHF"]

# Validation hook (to be replaced with your Pydantic models)

def validate_json(obj: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    try:
        # TODO: replace with Pydantic model validation
        json.dumps(obj)
        return True, None
    except Exception as e:
        return False, str(e)

# Dual save policy placeholder: user dir + app dir

def save_json_dual(obj: Dict[str, Any], base_id: str, user_root: Path, app_root: Path) -> Tuple[Path, Path]:
    user_root.mkdir(parents=True, exist_ok=True)
    app_root.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    user_path = user_root / f"{base_id}_{ts}.json"
    app_path = app_root / f"{base_id}.json"
    # Write files
    user_path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    app_path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return user_path, app_path

# Reindex placeholder invoking external script/service if present

def reindex_all(roots: List[Path], db_path: Path) -> bool:
    try:
        # If project exposes a service module, prefer it
        try:
            from service import reindex_all as svc_reindex  # type: ignore
# --- atomic write helper (added by patch) ---
from pathlib import Path as _PathForAtomic
def _atomic_write_text(path: _PathForAtomic, text: str) -> None:
    tmp = _PathForAtomic(str(path) + ".tmp")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
            svc_reindex([str(r) for r in roots], str(db_path))
            return True
        except Exception:
            # Minimal local reindex: scan roots for *.json and build a simple table
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cur.execute("CREATE TABLE IF NOT EXISTS pratiche (id TEXT PRIMARY KEY, titolo TEXT, stato TEXT, updated_at TEXT, path TEXT)")
            cur.execute("DELETE FROM pratiche")
            total = 0
            for root in roots:
                for p in root.rglob("*.json"):
                    try:
                        data = json.loads(p.read_text(encoding="utf-8"))
                        pid = str(data.get("id") or data.get("id_pratica") or p.stem)
                        titolo = str(data.get("titolo") or data.get("oggetto") or "(senza titolo)")
                        stato = str(data.get("stato") or data.get("status") or "-")
                        mtime = datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec='seconds')
                        cur.execute("INSERT OR REPLACE INTO pratiche (id, titolo, stato, updated_at, path) VALUES (?,?,?,?,?)",
                                    (pid, titolo, stato, mtime, str(p)))
                        total += 1
                    except Exception:
                        continue
            conn.commit()
            conn.close()
            debug(f"Reindex complete: {total} records")
            return True
    except Exception as e:
        debug(f"Reindex error: {e}")
        return False

# ----------------------- Data Model ----------------------- #

@dataclass
class Practice:
    id: str
    titolo: str = ""
    stato: str = ""
    updated_at: str = ""
    path: Optional[str] = None

class PracticeTableModel(QAbstractTableModel):
    HEADERS = ["ID", "Titolo", "Stato", "Aggiornato"]

    def __init__(self, rows: List[Practice]):
        super().__init__()
        self._rows = rows

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 4

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid():
            return None
        r = self._rows[index.row()]
        c = index.column()
        if role in (Qt.DisplayRole, Qt.EditRole):
            return [r.id, r.titolo, r.stato, r.updated_at][c]
        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.HEADERS[section]
        return None

    def practice_at(self, row: int) -> Optional[Practice]:
        if 0 <= row < len(self._rows):
            return self._rows[row]
        return None

    def set_rows(self, rows: List[Practice]):
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()

# ----------------------- Loaders ----------------------- #

def load_from_sqlite(db_path: Path) -> List[Practice]:
    if not db_path.exists():
        return []
    rows: List[Practice] = []
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        # Try common schema; otherwise attempt to infer columns
        try:
            cur.execute("SELECT id, titolo, stato, updated_at, path FROM pratiche ORDER BY updated_at DESC")
        except sqlite3.OperationalError:
            # Fallback: try a simpler projection
            cur.execute("PRAGMA table_info(pratiche)")
            cols = [c[1] for c in cur.fetchall()]
            id_col = "id_pratica" if "id_pratica" in cols else "id"
            title_col = "titolo" if "titolo" in cols else ("oggetto" if "oggetto" in cols else cols[1])
            state_col = "stato" if "stato" in cols else ("status" if "status" in cols else "")
            updated_col = "updated_at" if "updated_at" in cols else ("data_aggiornamento" if "data_aggiornamento" in cols else "")
            path_col = "path" if "path" in cols else ""
            sel = ", ".join([x for x in (id_col, title_col, state_col, updated_col, path_col) if x])
            cur.execute(f"SELECT {sel} FROM pratiche")
        for row in cur.fetchall():
            vals = list(row) + [None] * (5 - len(row))
            pid, titolo, stato, updated_at, path = vals[:5]
            rows.append(Practice(str(pid), str(titolo or ""), str(stato or ""), str(updated_at or ""), str(path) if path else None))
        conn.close()
    except Exception as e:
        debug(f"SQLite load error: {e}")
    return rows


def scan_roots_for_json(roots: List[Path]) -> List[Practice]:
    rows: List[Practice] = []
    for root in roots:
        if not root.exists():
            continue
        for p in root.rglob("*.json"):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                pid = str(data.get("id") or data.get("id_pratica") or p.stem)
                titolo = str(data.get("titolo") or data.get("oggetto") or "(senza titolo)")
                stato = str(data.get("stato") or data.get("status") or "-")
                mtime = datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec='seconds')
                rows.append(Practice(pid, titolo, stato, mtime, str(p)))
            except Exception:
                continue
    rows.sort(key=lambda r: r.updated_at, reverse=True)
    return rows

# ----------------------- Details Panel ----------------------- #

class DetailsPanel(QWidget):
    requestSave = Signal(dict)

    def __init__(self):
        super().__init__()
        self.current_obj: Dict[str, Any] = {}
        self.current_path: Optional[Path] = None
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # Currency selector
        currency_box = QHBoxLayout()
        currency_label = QLabel("Valuta:")
        self.currency_combo = QComboBox()
        self.currency_combo.addItems(CurrencyRegistry.allowed())
        currency_box.addWidget(currency_label)
        currency_box.addWidget(self.currency_combo)
        currency_box.addStretch(1)
        layout.addLayout(currency_box)

        # Key fields (simple dynamic form from JSON)
        self.form_group = QGroupBox("Dettagli")
        self.form_layout = QFormLayout()
        self.form_group.setLayout(self.form_layout)
        layout.addWidget(self.form_group)

        # Raw JSON viewer
        self.raw = QPlainTextEdit()
        self.raw.setReadOnly(False)  # allow edit for MVP; can lock later
        self.raw.setPlaceholderText("{\n  ... JSON della pratica ...\n}")
        self.raw.setTabChangesFocus(False)
        layout.addWidget(self.raw, 1)

        # Save button
        btns = QHBoxLayout()
        self.btn_save = QPushButton("Salva")
        self.btn_save.clicked.connect(self.on_save)
        btns.addStretch(1)
        btns.addWidget(self.btn_save)
        layout.addLayout(btns)

    def set_practice(self, path: Optional[str]):
        self.form_clear()
        self.current_obj = {}
        self.current_path = Path(path) if path else None
        if path and Path(path).exists():
            try:
                self.current_obj = json.loads(Path(path).read_text(encoding="utf-8"))
            except Exception as e:
                QMessageBox.warning(self, "Errore", f"Impossibile leggere JSON:\n{e}")
                self.current_obj = {}
        self.populate_from_json()

    def form_clear(self):
        while self.form_layout.rowCount():
            self.form_layout.removeRow(0)

    def populate_from_json(self):
        obj = self.current_obj or {}
        # Show some common fields if present
        for key in ("id", "id_pratica", "titolo", "oggetto", "stato", "status", "importo", "valuta"):
            if key in obj:
                line = QLineEdit(str(obj.get(key)))
                line.setReadOnly(False)
                line.editingFinished.connect(lambda k=key, w=line: self.update_key(k, w.text()))
                self.form_layout.addRow(QLabel(key), line)
        # Raw JSON
        try:
            self.raw.setPlainText(json.dumps(obj, ensure_ascii=False, indent=2))
        except Exception:
            self.raw.setPlainText("{}")

    def update_key(self, key: str, value: str):
        self.current_obj[key] = value
        # Keep raw JSON in sync (best effort)
        try:
            self.raw.setPlainText(json.dumps(self.current_obj, ensure_ascii=False, indent=2))
        except Exception:
            pass

    def on_save(self):
        # Prefer raw editor as source of truth
        try:
            obj = json.loads(self.raw.toPlainText())
        except Exception as e:
            QMessageBox.critical(self, "JSON non valido", str(e))
            return
        ok, err = validate_json(obj)
        if not ok:
            QMessageBox.critical(self, "Validazione fallita", err or "Errore di validazione")
            return
        self.requestSave.emit(obj)

# ----------------------- Main Window ----------------------- #

class MainWindow(QMainWindow):
    def __init__(self, db_path: Path, roots: List[Path], user_root: Path, app_root: Path):
        super().__init__()
        self.db_path = db_path
        self.roots = roots
        self.user_root = user_root
        self.app_root = app_root
        self.setWindowTitle("Gestione Pratiche — PySide6")
        self.resize(1200, 750)
        self._build_ui()
        self.refresh_models()

    # UI
    def _build_ui(self):
        self._build_toolbar()
        splitter = QSplitter()

        # Table
        self.table = QTableView()
        self.table.setSortingEnabled(True)
        self.table.doubleClicked.connect(self.on_open_selected)
        self.model = PracticeTableModel([])
        self.proxy = QSortFilterProxyModel()
        self.proxy.setSourceModel(self.model)
        self.table.setModel(self.proxy)
        splitter.addWidget(self.table)

        # Details
        self.details = DetailsPanel()
        self.details.requestSave.connect(self.on_save_json)
        splitter.addWidget(self.details)
        splitter.setStretchFactor(1, 1)

        self.setCentralWidget(splitter)

    def _build_toolbar(self):
        tb = QToolBar("Azioni")
        tb.setIconSize(tb.iconSize())
        self.addToolBar(tb)

        act_new = QAction(self.style().standardIcon(QStyle.SP_FileIcon), "Nuova", self)
        act_new.triggered.connect(self.on_new)
        tb.addAction(act_new)

        act_open = QAction(self.style().standardIcon(QStyle.SP_DirOpenIcon), "Apri", self)
        act_open.triggered.connect(self.on_open)
        tb.addAction(act_open)

        act_save = QAction(self.style().standardIcon(QStyle.SP_DialogSaveButton), "Salva", self)
        act_save.triggered.connect(lambda: self.details.on_save())
        tb.addAction(act_save)

        tb.addSeparator()

        act_reindex = QAction(QIcon(), "Reindicizza", self)
        act_reindex.triggered.connect(self.on_reindex)
        tb.addAction(act_reindex)

        act_refresh = QAction(self.style().standardIcon(QStyle.SP_BrowserReload), "Aggiorna", self)
        act_refresh.triggered.connect(self.refresh_models)
        tb.addAction(act_refresh)

        tb.addSeparator()

        act_quit = QAction(self.style().standardIcon(QStyle.SP_DialogCloseButton), "Esci", self)
        act_quit.triggered.connect(self.close)
        tb.addAction(act_quit)

    # Data refresh
    def refresh_models(self):
        rows = load_from_sqlite(self.db_path)
        if not rows:
            rows = scan_roots_for_json(self.roots)
        self.model.set_rows(rows)
        if rows:
            self.table.selectRow(0)
            self._load_details_from_row(0)

    def _load_details_from_row(self, row: int):
        pr = self.model.practice_at(self.proxy.mapToSource(self.proxy.index(row, 0)).row()) if self.proxy else self.model.practice_at(row)
        if pr and pr.path:
            self.details.set_practice(pr.path)
        else:
            self.details.set_practice(None)

    # Actions
    def on_new(self):
        # Minimal skeleton; customize with your fields
        new_obj = {
            "id": f"pratica_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "titolo": "Nuova pratica",
            "stato": "bozza",
            "valuta": self.details.currency_combo.currentText(),
            "created_at": datetime.now().isoformat(timespec='seconds'),
        }
        self.details.current_obj = new_obj
        self.details.current_path = None
        self.details.populate_from_json()

    def on_open(self):
        path, _ = QFileDialog.getOpenFileName(self, "Apri pratica JSON", str(self.roots[0] if self.roots else Path.cwd()), "JSON (*.json)")
        if path:
            self.details.set_practice(path)

    def on_open_selected(self, index: QModelIndex):
        row = index.row()
        self._load_details_from_row(row)

    def on_write_pratica(self, obj: dict):
        from datetime import datetime
        base_id = str(obj.get('id') or obj.get('id_pratica') or f"pratica_{datetime.now():%Y%m%d_%H%M%S}")
        try:
            # 1) se editing di un file reale, salva accanto (overwrite atomico)
            if getattr(self.details, 'current_path', None):
                p = Path(self.details.current_path)
                js = json.dumps(obj, ensure_ascii=False, indent=2)
                _atomic_write_text(p, js)
            # 2) dual-save (versionata + backup app)
            user_path, app_path = save_json_dual(obj, base_id, self.user_root, self.app_root)
            QMessageBox.information(self, 'Salvato', f'Salvato in:\n{user_path}\n{app_path}')
            try:
                reindex_all(self.roots, self.db_path)
            finally:
                self.refresh_models()
        except Exception as e:
            QMessageBox.critical(self, 'Errore salvataggio', str(e))

    def on_reindex(self):
        ok = reindex_all(self.roots, self.db_path)
        if ok:
            QMessageBox.information(self, "Reindicizzazione", "Completata con successo")
            self.refresh_models()
        else:
            QMessageBox.critical(self, "Reindicizzazione", "Errore durante la reindicizzazione")

# ----------------------- CLI & App ----------------------- #

def parse_args():
    ap = argparse.ArgumentParser(description="UI Gestione Pratiche (PySide6)")
    ap.add_argument("--db", type=str, default="indice.sqlite", help="Percorso database SQLite dell'indice")
    ap.add_argument("--roots", nargs="*", default=["."], help="Root directory dove cercare i JSON delle pratiche")
    ap.add_argument("--user-root", type=str, default="./utente_pratiche", help="Cartella salvataggi utente (versionati)")
    ap.add_argument("--app-root", type=str, default="./app_pratiche", help="Cartella backup app (sovrascrivibile)")
    return ap.parse_args()


def main():
    args = parse_args()
    db_path = Path(args.db).resolve()
    roots = [Path(r).resolve() for r in (args.roots or ["."])]
    user_root = Path(args.user_root).resolve()
    app_root = Path(args.app_root).resolve()

    app = QApplication(sys.argv)
    win = MainWindow(db_path, roots, user_root, app_root)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()