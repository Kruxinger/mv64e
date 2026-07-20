# certs/

Dieser Ordner enthält die TLS-Zertifikate (bzw. Zertifikatsketten) eurer Institution,
die für die verifizierten HTTPS-Verbindungen zu Keycloak, gPAS und DIZ benötigt werden.
Die Dateien sind bewusst **nicht** Teil des Repos (siehe `.gitignore`), da sie interne
Hostnamen preisgeben.

Lege hier folgende Dateien ab (Dateinamen wie vom Code erwartet):

| Datei | Verwendet von | Zweck |
|---|---|---|
| `medver-keycloak-srv-med-uni-muenchen-de-zertifikatskette.pem` | `utils/keycloak.py` | Keycloak Token-Endpoint |
| `srvdiz103p-zertifikatskette.pem` | `utils/consent.py` | DIZ Consent-Endpoint |
| `diz.crt` | `utils/check_services.py` | DIZ Health-Check |
| `gpas.crt` | `tan_service.py`, `utils/tan_service.py` | gPAS TAN-Generierung |

Jede Datei ist die öffentliche Zertifikatskette (PEM) des jeweiligen Servers, keine
privaten Schlüssel. Exportiere sie z. B. mit:

```bash
openssl s_client -showcerts -connect <host>:<port> </dev/null 2>/dev/null \
  | openssl x509 -outform PEM > certs/<name>.pem
```
