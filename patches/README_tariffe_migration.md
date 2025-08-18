# Migrazione `pratica_tariffe` e stabilizzazione CRUD

Questo pacchetto stabilizza il flusso CRUD con SQLite e migra `pratica_tariffe`.

## Cosa include
- `repo_sqlite.py` stabile:
  - `merge_children` filtra i campi contro lo schema reale e rispetta `pos/ordine`.
  - Loader compatibile con context manager (`with get_connection(...) as con:`).
- `patches/003_tariffe_migration_final.sql`:
  - Ricostruzione tabella, pulizia duplicati, indici UNIQUE (uid e (id_pratica, ordine) WHERE ordine IS NOT NULL), trigger `ordine ← pos`.
- `patches/postcheck_tariffe.sql`: verifica schema/indici/trigger/duplicati.

## Requisiti
- SQLite ≥ 3.37 (ok 3.37.2).

## Backup
cp archivio/0gp.sqlite archivio/0gp.sqlite.bak.$(date +%F_%H%M%S)

## Migrazione
sqlite3 archivio/0gp.sqlite < patches/003_tariffe_migration_final.sql

## Post-check
sqlite3 archivio/0gp.sqlite < patches/postcheck_tariffe.sql

## Note
- Il trigger garantisce `ordine = pos` quando non fornito.
- Se vuoi persistere campi extra (`tipo_tariffa`, `valore`, `note`), aggiungi le colonne con `ALTER TABLE` e verranno salvati.
