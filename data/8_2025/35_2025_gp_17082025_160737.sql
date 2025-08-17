-- Export pratica 35/2025
-- Database: /home/robert/StudioLegalePalmieri/AMMINISTRAZIONE/StudioLegaleAssociato/Gestione_pratiche/0GP/archivio/0gp.sqlite
-- Generato: 2025-08-17T16:07:37
-- Tabelle coinvolte: attivita, documenti, history, pratica_avvocati, pratica_tariffe, pratiche, scadenze
BEGIN;
-- attivita
DELETE FROM attivita WHERE id_pratica='35/2025';
-- documenti
DELETE FROM documenti WHERE id_pratica='35/2025';
-- history
DELETE FROM history WHERE id_pratica='35/2025';
-- pratica_avvocati
DELETE FROM pratica_avvocati WHERE id_pratica='35/2025';
-- pratica_tariffe
DELETE FROM pratica_tariffe WHERE id_pratica='35/2025';
-- pratiche
DELETE FROM pratiche WHERE id_pratica='35/2025';
INSERT INTO pratiche (id_pratica, created_at, updated_at, anno, numero, tipo_pratica, settore, materia, referente_email, referente_nome, preventivo, note, raw_json, titolo, stato) VALUES ('35/2025', '2025-08-17 14:07:37', '2025-08-17 14:07:37', NULL, NULL, NULL, NULL, NULL, NULL, NULL, 0, '', '{"id_pratica": "35/2025", "nome_pratica": "71_352025", "percorso_pratica": "/home/robert/StudioLegalePalmieri/AMMINISTRAZIONE/StudioLegaleAssociato/Gestione_pratiche/71_17082025/71_352025", "data_apertura": null, "data_chiusura": null, "valore_pratica": "", "tipo_pratica": null, "settore_pratica": null, "materia_pratica": null, "avvocato_referente": null, "avvocato_in_mandato": [], "preventivo_inviato": false, "note": "", "tipo_tariffe": [], "_tariffe_widgets": [], "settore_element": null, "materia_element": null, "avv_referente_element": null, "avv_mandato_element": [], "refresh_settori": null, "refresh_materie": null, "refresh_avvocati": null, "tariffe_contenzioso": {"Base": [{"note": "", "tot": ""}], "Forfait": [{"note": "", "tot": ""}], "A Percentuale": [{"note": "", "tot": "", "valore": "", "percentuale": ""}], "A Risultato": [{"note": "", "tot": ""}], "Oraria": [{"note": "", "tot": "", "tariffa_oraria": "", "tempo_stimato": ""}], "Abbonamento": [{"note": "", "tot": ""}]}, "totale_contenzioso": 0.0, "totale_stragiudiziale": 0.0, "totale_generale": 0.0, "tariffe_stragiudiziale": {"Base": [{"note": "", "tot": ""}], "Forfait": [{"note": "", "tot": ""}], "A Percentuale": [{"note": "", "tot": "", "valore": "", "percentuale": ""}], "A Risultato": [{"note": "", "tot": ""}], "Oraria": [{"note": "", "tot": "", "tariffa_oraria": "", "tempo_stimato": ""}], "Abbonamento": [{"note": "", "tot": ""}]}, "scadenze": [{"descrizione": "", "data_inizio": "", "data_scadenza": "", "minuti_prima_allert": 30, "durata_stimata": 0, "durata_effettiva": null, "scadenza": false, "tariffa_oraria": 300.0, "tariffa_stimata": "0.00", "tariffa_effettiva": "0.00", "id_evento": ""}], "scadenze_totale_durata_stimata": 0, "scadenze_totale_tariffa_stimata": 0.0, "scadenze_totale_tariffa_effettiva": 0.0, "updated_at": "2025-08-17T16:07:37"}', NULL, NULL);
-- scadenze
DELETE FROM scadenze WHERE id_pratica='35/2025';
INSERT INTO scadenze (id, id_pratica, data_scadenza, descrizione, note, completata, uid, pos) VALUES (43, '35/2025', '', '', NULL, NULL, '0ac5c0358fdc4533b87f7d9a32fb0383', 0);
COMMIT;
