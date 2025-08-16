-- db_schema.sql
--
-- Schema definition for the 0GP SQLite database.  This file defines the
-- minimal set of tables necessary to persist the application domain in a
-- relational form.  Each table corresponds to a JSON object or list in
-- the existing JSON archive.  This schema is intentionally simple to
-- support quick ingestion and export of individual practices.

-- Enable foreign keys for referential integrity.
PRAGMA foreign_keys = ON;

-- Table of practices.  The natural key is the `id_pratica` (e.g. "8_2025").
CREATE TABLE IF NOT EXISTS pratiche (
  id_pratica      TEXT PRIMARY KEY,
  data_apertura   TEXT,
  data_chiusura   TEXT,
  tipo            TEXT,
  settore         TEXT,
  materia         TEXT,
  referente       TEXT,
  is_preventivo   INTEGER DEFAULT 0,
  note            TEXT,
  created_at      TEXT DEFAULT (datetime('now')),
  updated_at      TEXT DEFAULT (datetime('now'))
);

-- Many‑to‑many association between a practice and the lawyers involved.
-- The composite primary key prevents duplicate (role/email) pairs.
CREATE TABLE IF NOT EXISTS pratica_avvocati (
  id_pratica  TEXT NOT NULL,
  ruolo       TEXT NOT NULL,
  email       TEXT NOT NULL,
  nome        TEXT,
  PRIMARY KEY (id_pratica, ruolo, email),
  FOREIGN KEY (id_pratica) REFERENCES pratiche(id_pratica) ON DELETE CASCADE
);

-- Tariff information associated with a practice.  `ordine` preserves the
-- ordering from the original list.  `tipo_tariffa` describes the tariff type.
CREATE TABLE IF NOT EXISTS pratica_tariffe (
  id_pratica   TEXT NOT NULL,
  ordine       INTEGER NOT NULL,
  tipo_tariffa TEXT NOT NULL,
  PRIMARY KEY (id_pratica, ordine),
  FOREIGN KEY (id_pratica) REFERENCES pratiche(id_pratica) ON DELETE CASCADE
);

-- Activities performed within a practice.  Each activity has its own
-- autoincremented identifier to support multiple entries for the same
-- practice.  Timestamp fields are stored as ISO 8601 strings.
CREATE TABLE IF NOT EXISTS attivita (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  id_pratica  TEXT NOT NULL,
  inizio      TEXT,
  fine        TEXT,
  descrizione TEXT,
  durata_min  INTEGER,
  tariffa_eur REAL,
  tipo        TEXT,
  note        TEXT,
  FOREIGN KEY (id_pratica) REFERENCES pratiche(id_pratica) ON DELETE CASCADE
);

-- Deadlines associated with a practice.
CREATE TABLE IF NOT EXISTS scadenze (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  id_pratica     TEXT NOT NULL,
  data_scadenza  TEXT,
  descrizione    TEXT,
  note           TEXT,
  completata     INTEGER DEFAULT 0,
  FOREIGN KEY (id_pratica) REFERENCES pratiche(id_pratica) ON DELETE CASCADE
);

-- Documents belonging to a practice.  The `path` stores the relative
-- filesystem path inside the archive; `hash` can be used for de‑duplication.
CREATE TABLE IF NOT EXISTS documenti (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  id_pratica  TEXT NOT NULL,
  path        TEXT NOT NULL,
  categoria   TEXT,
  note        TEXT,
  hash        TEXT,
  FOREIGN KEY (id_pratica) REFERENCES pratiche(id_pratica) ON DELETE CASCADE
);

-- History log captures actions taken on a practice.  `payload` can be
-- arbitrary JSON text describing the event.  The `ts` column stores
-- timestamps as ISO 8601 strings.
CREATE TABLE IF NOT EXISTS history (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  id_pratica TEXT NOT NULL,
  ts         TEXT,
  actor      TEXT,
  event      TEXT,
  payload    TEXT,
  FOREIGN KEY (id_pratica) REFERENCES pratiche(id_pratica) ON DELETE CASCADE
);

-- Lookup tables.  These are populated from the existing JSON files and
-- provide value sets for types, sectors, subjects, and lawyers.  The
-- primary key ensures uniqueness.  Additional columns can be added
-- later as needed.
CREATE TABLE IF NOT EXISTS lookup_tipi_pratica (
  codice TEXT PRIMARY KEY,
  descrizione TEXT
);

CREATE TABLE IF NOT EXISTS lookup_settori (
  codice TEXT PRIMARY KEY,
  descrizione TEXT
);

CREATE TABLE IF NOT EXISTS lookup_materie (
  codice TEXT PRIMARY KEY,
  descrizione TEXT
);

CREATE TABLE IF NOT EXISTS lookup_avvocati (
  email TEXT PRIMARY KEY,
  nome TEXT,
  ruolo TEXT
);

-- Id counter table used to generate sequential practice identifiers per year.
CREATE TABLE IF NOT EXISTS id_counter (
  anno     INTEGER PRIMARY KEY,
  last_n   INTEGER DEFAULT 0
);

-- Indices to speed up common queries.  These indices mirror the
-- retrieval patterns in the JSON‑based implementation, such as filtering
-- activities by practice id or ordering practices by opening date.
CREATE INDEX IF NOT EXISTS idx_attivita_id_pratica ON attivita(id_pratica);
CREATE INDEX IF NOT EXISTS idx_scadenze_id_pratica ON scadenze(id_pratica);
CREATE INDEX IF NOT EXISTS idx_documenti_id_pratica ON documenti(id_pratica);
CREATE INDEX IF NOT EXISTS idx_history_id_pratica ON history(id_pratica);
