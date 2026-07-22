# utils/ca_bundle.py
import os
import tempfile
import threading

import certifi

_EXTRA_CERT_PATH = os.path.join(
    os.path.dirname(__file__), "..", "certs", "geant-tls-rsa-1-intermediate.pem"
)

_bundle_path = None
_lock = threading.Lock()


def get_ca_bundle():
    """
    Standard-CA-Store (certifi) + GEANT TLS RSA 1 Intermediate-Zertifikat.
    medver-keycloak liefert beim TLS-Handshake nur das Leaf-Zertifikat ohne
    Zwischenzertifikat aus, daher reicht der Standard-Store allein nicht.
    Das Intermediate ist stabil (gueltig bis 2039), im Gegensatz zum
    vorher gepinnten, sich staendig aendernden Leaf-Zertifikat.
    """
    global _bundle_path
    if _bundle_path is None:
        with _lock:
            if _bundle_path is None:
                with open(certifi.where(), "rb") as f:
                    bundle = f.read()
                with open(_EXTRA_CERT_PATH, "rb") as f:
                    bundle += b"\n" + f.read()
                fd, path = tempfile.mkstemp(suffix=".pem", prefix="mv64e-ca-bundle-")
                with os.fdopen(fd, "wb") as f:
                    f.write(bundle)
                _bundle_path = path
    return _bundle_path
