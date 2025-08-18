PRAGMA foreign_keys=OFF;
BEGIN TRANSACTION;

-- Drop vecchio trigger, se presente
DROP TRIGGER IF EXISTS trg_pratica_tariffe_set_ordine;

-- Tabella finale coerente
DROP TABLE IF EXISTS pratica_tariffe_final;
CREATE TABLE pratica_tariffe_final (
  id_pratica   TEXT    NOT NULL,
  uid          TEXT    NOT NULL,
  pos          INTEGER NOT NULL,
  ordine       INTEGER,
  PRIMARY KEY (id_pratica, uid),
  FOREIGN KEY (id_pratica) REFERENCES pratiche(id_pratica) ON DELETE CASCADE
);

-- Copia dati minimi dalla tabella corrente
INSERT INTO pratica_tariffe_final (id_pratica, uid, pos, ordine)
SELECT id_pratica, uid, pos, ordine
FROM pratica_tariffe;

-- Sostituzione tabella
DROP TABLE pratica_tariffe;
ALTER TABLE pratica_tariffe_final RENAME TO pratica_tariffe;

-- Pulizia duplicati
-- 1) uid duplicati -> rinomina i successivi
WITH c AS (
  SELECT rowid, uid,
         ROW_NUMBER() OVER (PARTITION BY uid ORDER BY rowid) AS rn
  FROM pratica_tariffe
)
UPDATE pratica_tariffe
SET uid = uid || '-' || rowid
WHERE rowid IN (SELECT rowid FROM c WHERE rn > 1);

-- 2) (id_pratica, ordine) duplicati -> azzera oltre il primo
WITH d AS (
  SELECT t.rowid
  FROM pratica_tariffe t
  WHERE t.ordine IS NOT NULL
    AND EXISTS (
      SELECT 1 FROM pratica_tariffe x
      WHERE x.id_pratica = t.id_pratica
        AND x.ordine = t.ordine
        AND x.rowid < t.rowid
    )
)
UPDATE pratica_tariffe SET ordine = NULL WHERE rowid IN (SELECT rowid FROM d);
-- riempi gli ordine mancanti con pos
UPDATE pratica_tariffe SET ordine = pos WHERE ordine IS NULL;

-- Indici
DROP INDEX IF EXISTS uq_pratica_tariffe_uid;
DROP INDEX IF EXISTS uq_pratica_tariffe_ordine;
DROP INDEX IF EXISTS idx_pratica_tariffe_pos;

CREATE UNIQUE INDEX IF NOT EXISTS uq_pratica_tariffe_uid
ON pratica_tariffe(uid);

CREATE UNIQUE INDEX IF NOT EXISTS uq_pratica_tariffe_ordine
ON pratica_tariffe(id_pratica, ordine) WHERE ordine IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_pratica_tariffe_pos
ON pratica_tariffe(id_pratica, pos);

-- Trigger: se ordine è NULL alla insert, mettilo = pos
CREATE TRIGGER IF NOT EXISTS trg_pratica_tariffe_set_ordine
AFTER INSERT ON pratica_tariffe
FOR EACH ROW WHEN NEW.ordine IS NULL
BEGIN
  UPDATE pratica_tariffe SET ordine = NEW.pos WHERE rowid = NEW.rowid;
END;

COMMIT;
PRAGMA foreign_keys=ON;
