# Setup
Bevor die App läuft, müssen die institutionseigenen TLS-Zertifikate unter `certs/`
abgelegt werden (siehe `certs/README.md`) sowie eine `.env` nach Vorbild von
`.sample_env` angelegt werden.

# Infos für die Dokumentation
Der Import der Daten aus Onkostar läuft über das Formular "DNPM Klinik/Anamnese".  
**Hinweis**: Es werden nur "DNPM Klinik/Anamnese" Formulare mit einem validen Datum in Betracht gezogen. Damit werden 
auch die durch das Plugin automatisch erzeugten Formulare übersprungen.
Folgende Daten werden aus Onkostar übernommen:
* AGS, Abrechnungstyp (GKS, PKS,...), Gender, Geburtsdatum aus den **Patientendaten** direkt
* Der MV Consent aus "DNPM Klinik/Anamnese" &rarr; "Consent" &rarr; "Consent MV §64e":  
 Es muss also im "DNPM Klinik/Anamnese" Formular der Consentverweis gesetzt sein, ein Consent im Verlauf allein 
reicht nicht aus.
* Der Broad Consent wird direkt vom DIZ angefragt
* ECOG: Hier wird der letzte, also zeitlich jüngste/aktuellste Status aus "DNPM Klinik/Anamnese" genutzt
* ICD-10-Diagnose (inkl. Datum) , ICD-O-3-Lokalisation und ICD-O-3-Histologie werden ebenfalls aus "DNPM Klinik/Anamnese" übernommen, wobei
der Verweis auf die passende Diagnose beim anlegen des Formulars passiert
* Die Art der Sequenzierung (WES, Panel,...) wird aus dem zeitlich nächsten Formular "Molekulargenetische Untersuchung" gezogen
* Als "molecularBoardDecisionDate" wird das Datum des nach dem "DNPM Klinik/Anamnese" nächsten Indikationsboard genommen
* "decisionToInclude" wird bestimmt durch: "Ja", wenn nach dem Indikationsboard noch ein "MV GenomSeq" stattgefunden hat
