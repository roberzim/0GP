.headers on
.mode column

SELECT '=== table_info(pratica_tariffe) ===' AS info;
PRAGMA table_info(pratica_tariffe);

SELECT '=== indici pratica_tariffe ===' AS info;
SELECT name, sql
FROM sqlite_master
WHERE type='index' AND tbl_name='pratica_tariffe';

SELECT '=== trigger pratica_tariffe ===' AS info;
SELECT name, sql
FROM sqlite_master
WHERE type='trigger' AND tbl_name='pratica_tariffe';

SELECT '=== conteggio record ===' AS info;
SELECT COUNT(*) AS n FROM pratica_tariffe;

SELECT '=== duplicati (id_pratica, ordine) ===' AS info;
SELECT id_pratica, ordine, COUNT(*) AS c
FROM pratica_tariffe
WHERE ordine IS NOT NULL
GROUP BY id_pratica, ordine
HAVING c > 1
ORDER BY id_pratica, ordine;
