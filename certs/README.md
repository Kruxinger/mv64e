# Zertifikats-Situation mv64e / med.uni-muenchen.de

Diese App spricht mit drei externen Services im Uniklinikum-Netz. Alle drei
sitzen hinter unterschiedlichen, jeweils eigenwilligen TLS-Setups. Wer hier
naiv `verify=True` oder ein einzelnes gepinntes Zertifikat erwartet, tappt in
eine von drei verschiedenen Fallen.

## Die drei Services und ihre jeweilige Falle

| Service | Host | Problem | Lösung |
|---|---|---|---|
| **Keycloak** | `medver-keycloak.srv.med.uni-muenchen.de` | Sendet beim TLS-Handshake nur das Leaf-Zertifikat, **nicht** das Zwischenzertifikat. Ausstellende CA ist `GEANT TLS RSA 1` (HARICA/Hellenic Academic and Research Institutions CA) — eine **öffentliche**, in `certifi` verankerte Root, aber ohne das Intermediate im Handshake kann kein Standard-Client die Kette schließen (`unable to get local issuer certificate`). | `geant-tls-rsa-1-intermediate.pem` (gültig bis 2039) |
| **gPAS** | `srvdiz089p.srv.med.uni-muenchen.de` | **Selbstsigniertes Zertifikat** (Issuer == Subject). Keine Kette, keine Root — kann grundsätzlich nur durch exaktes Pinning vertraut werden. Bricht garantiert wieder, sobald der Server das Zertifikat neu generiert (keine Vorwarnung, keine Rotation-Automatik). | `gpas-srvdiz089p-selfsigned.pem` (gültig bis 2035) — **muss manuell ersetzt werden, wenn gPAS das Zertifikat erneuert** |
| **DIZ** | `bc.diz.med.uni-muenchen.de` (antwortet intern als `SRVDIZ103P`) | Ausgestellt von der **hausinternen PKI** des Klinikums (`Klinikum der Universitaet Muenchen SubCA G3`, Root `...Root CA G2`) — taucht naturgemäß in keinem öffentlichen Trust-Store auf. | `diz-klinikum-subca-g3.pem` (gültig bis 2042) |

## Die zentrale Architekturentscheidung

`utils/ca_bundle.py` → `get_ca_bundle()` baut zur Laufzeit einmalig ein
kombiniertes CA-Bundle: `certifi`-Standardstore + **alle** `*.pem`-Dateien in
diesem Verzeichnis. Verwendet wird das in `utils/keycloak.py`,
`utils/tan_service.py`, `utils/consent.py`, `utils/check_services.py`
(jeweils `verify=get_ca_bundle()`).

**Warum nicht einfach das Leaf-Zertifikat jedes Servers pinnen** (so war es
früher: `key_cloak.crt`, `gpas.crt`, `diz.crt`)? Weil Leaf-Zertifikate
typischerweise alle paar Monate/1 Jahr rotieren, während Intermediate-/
interne-CA-Zertifikate viele Jahre stabil bleiben. Der ursprüngliche Bug
("KeyCloak konnte nicht geladen werden... certificate verify failed") kam
genau daher: das gepinnte Leaf-Zertifikat war schlicht veraltet. Die einzige
Ausnahme, wo Leaf-Pinning unvermeidbar bleibt, ist **gPAS**, weil es
selbstsigniert ist — da gibt es keine stabilere Alternative.

## Netzwerk-Kontext (wichtig für Diagnose)

- Alle drei Hosts sind **nur aus dem Uniklinikum-internen Netz erreichbar**
  (nicht aus Cloud-/Sandbox-Umgebungen wie Claude Code Web-Sessions — die
  Egress-Allowlist blockt das grundsätzlich).
- Der Zugriff läuft über einen **Fortinet-Forward-Proxy**
  (`192.168.24.30:8080` bzw. `mitproxy0.srv.med.uni-muenchen.de:8080` je
  nach Quellsystem, siehe `docker-compose.yml`). Der Proxy tunnelt per HTTP
  CONNECT und macht **kein** TLS-Interception (verifiziert: die echten
  Origin-Zertifikate kommen unverändert durch — sonst hätten wir nicht die
  echte GEANT-Kette gesehen).
- Diagnosebefehl bei neuen Zertifikatsproblemen (von einer Maschine mit
  Netzzugriff, z.B. `mitmolpat`):
  ```bash
  openssl s_client -proxy <proxy-ip>:8080 -connect <host>:443 -servername <host> </dev/null 2>/dev/null | grep -A4 "Certificate chain"
  ```
  Zeigt Subject/Issuer der gesendeten Kette. Wenn Issuer == Subject →
  selbstsigniert, nur Pinning möglich. Wenn Issuer eine unbekannte/interne
  CA ist und nur ein Kettenglied kommt → fehlendes Intermediate, per
  AIA-Extension nachschlagen:
  ```bash
  openssl s_client -proxy <proxy-ip>:8080 -connect <host>:443 -servername <host> </dev/null 2>/dev/null | openssl x509 -noout -text | grep -A2 "Authority Information Access"
  ```
  Liefert eine `CA Issuers`-URL (oft `http://ca.info.med.uni-muenchen.de/AIA/...`
  für interne CAs, oder öffentliche Repos für öffentliche CAs) zum
  Nachladen des fehlenden Zertifikats.

## Vorgehen, wenn ein neues Zertifikatsproblem auftaucht

1. Diagnose-Befehl oben ausführen (braucht Zugriff auf das interne Netz —
   ggf. den Nutzer bitten, das auszuführen und die Ausgabe zu posten, falls
   die aktuelle Session das nicht selbst kann).
2. Fehlendes Zertifikat besorgen (AIA-Link oder bei rein internen CAs:
   IT/PKI-Team fragen bzw. aus dem Windows-Zertifikatsspeicher eines
   domänengebundenen Rechners exportieren).
3. Als `.pem` unter `certs/<beschreibender-name>.pem` ablegen —
   `get_ca_bundle()` pickt es automatisch auf, **kein Code-Change nötig**.
4. Bei selbstsignierten Zertifikaten (wie gPAS): Fingerabdruck über einen
   vertrauenswürdigen Kanal verifizieren, bevor man ihn pinnt.

## Bekannte Nebenbaustellen (im selben Zuge mitgefixt)

- `utils/check_services.py`: Der gPAS-Health-Check rief früher
  `generate_tan("TEST001")` auf — `generate_tan()` validiert
  (`case_id.isdigit()`), sodass die nicht-numerische Test-ID die Funktion
  sofort mit `""` zurückkehren ließ, ohne Keycloak/gPAS je zu kontaktieren.
  Health-Check zeigte deshalb dauerhaft Fake-Grün. Jetzt numerische Test-ID
  (`GPAS_HEALTHCHECK_CASE_ID`, Default `"000000001"`) plus echte Prüfung
  auf nicht-leeren Rückgabewert.
- `app.py` `/logs`-Route: `Log.query.order_by(Log.timestamp.asc()).limit(200)`
  lieferte die 200 ältesten statt neuesten Einträge — bei mehr als 200
  Logzeilen zeigte die Seite dauerhaft nur uralte Historie. Jetzt `desc()`
  + Limit + Reverse für die Anzeige.
- Die vormals referenzierten `certs/gpas.crt` / `certs/diz.crt` existierten
  nie im Repo (nur `certs/key_cloak.crt` war real, aber veraltet) —
  DIZ/gPAS-Checks liefen also vorher ohnehin ins Leere (Datei nicht
  gefunden), unabhängig vom eigentlichen Zertifikatsproblem.
