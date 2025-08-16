PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS id_counter (
  anno INTEGER PRIMARY KEY,
  last_n INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS pratiche (
  id_pratica TEXT PRIMARY KEY,
  anno INTEGER,
  numero INTEGER,
  tipo_pratica TEXT,
  settore TEXT,
  materia TEXT,
  referente_email TEXT,
  referente_nome TEXT,
  preventivo INTEGER DEFAULT 0,
  note TEXT,
  created_at TEXT DEFAULT (datetime('now')),
  updated_at TEXT,
  raw_json TEXT   -- snapshot per round-trip UI
);

CREATE TABLE IF NOT EXISTS pratica_avvocati (
  id_pratica TEXT NOT NULL REFERENCES pratiche(id_pratica) ON DELETE CASCADE,
  email TEXT NOT NULL,
  nome TEXT,
  ruolo TEXT NOT NULL,
  PRIMARY KEY (id_pratica, email, ruolo)
);

CREATE TABLE IF NOT EXISTS pratica_tariffe (
  id_pratica TEXT NOT NULL REFERENCES pratiche(id_pratica) ON DELETE CASCADE,
  ordine INTEGER NOT NULL,
  tipo_tariffa TEXT,
  valore REAL,
  note TEXT,
  PRIMARY KEY (id_pratica, ordine)
);

CREATE TABLE IF NOT EXISTS attivita (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  id_pratica TEXT NOT NULL REFERENCES pratiche(id_pratica) ON DELETE CASCADE,
  inizio TEXT,
  fine TEXT,
  descrizione TEXT,
  durata_min INTEGER,
  tariffa_eur REAL,
  tipo TEXT,
  note TEXT
);
CREATE INDEX IF NOT EXISTS idx_attivita_pratica ON attivita(id_pratica);

CREATE TABLE IF NOT EXISTS scadenze (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  id_pratica TEXT NOT NULL REFERENCES pratiche(id_pratica) ON DELETE CASCADE,
  data_scadenza TEXT,
  descrizione TEXT,
  note TEXT,
  completata INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_scadenze_pratica ON scadenze(id_pratica);

CREATE TABLE IF NOT EXISTS documenti (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  id_pratica TEXT NOT NULL REFERENCES pratiche(id_pratica) ON DELETE CASCADE,
  path TEXT,         -- percorso file nel FS (es. app_pratiche/<id>/documenti/…)
  categoria TEXT,
  note TEXT,
  hash TEXT
);
CREATE INDEX IF NOT EXISTS idx_documenti_pratica ON documenti(id_pratica);

CREATE TABLE IF NOT EXISTS history (
  ts TEXT DEFAULT (datetime('now')),
  id_pratica TEXT NOT NULL REFERENCES pratiche(id_pratica) ON DELETE CASCADE,
  actor TEXT,
  event TEXT,
  payload TEXT
);
CREATE INDEX IF NOT EXISTS idx_history_pratica ON history(id_pratica);

