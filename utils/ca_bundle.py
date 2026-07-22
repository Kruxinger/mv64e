# utils/ca_bundle.py
import glob
import os
import tempfile
import threading

import certifi

_EXTRA_CERTS_DIR = os.path.join(os.path.dirname(__file__), "..", "certs")

_bundle_path = None
_lock = threading.Lock()


def get_ca_bundle():
    """
    Standard-CA-Store (certifi) + alle *.pem in certs/.

    Die internen/institutseigenen Endpunkte (Keycloak, gPAS, DIZ) liefern
    entweder eine unvollstaendige Zertifikatskette (fehlendes Intermediate)
    oder ein selbstsigniertes/institutsinternes Zertifikat, das in keinem
    oeffentlichen Trust-Store steht. Statt das sich staendig aendernde
    Leaf-Zertifikat jedes Endpunkts zu pinnen, werden hier die stabilen
    Zwischen-/Root-Zertifikate als zusaetzliche Trust-Anchor hinterlegt.
    """
    global _bundle_path
    if _bundle_path is None:
        with _lock:
            if _bundle_path is None:
                with open(certifi.where(), "rb") as f:
                    bundle = f.read()
                for cert_path in sorted(glob.glob(os.path.join(_EXTRA_CERTS_DIR, "*.pem"))):
                    with open(cert_path, "rb") as f:
                        bundle += b"\n" + f.read()
                fd, path = tempfile.mkstemp(suffix=".pem", prefix="mv64e-ca-bundle-")
                with os.fdopen(fd, "wb") as f:
                    f.write(bundle)
                _bundle_path = path
    return _bundle_path
