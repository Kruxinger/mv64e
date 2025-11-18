import logging
import os

import certifi
import requests
from models import db, ServiceStatus  # SQLAlchemy Models
from utils.keycloak import get_keycloak_token
from utils.tan_service import generate_tan


def check_services():
    """
    Prüft externe Services und speichert den Status in der DB.
    Läuft innerhalb eines Flask App Context.
    """
    services = {}

    # --- Keycloak ---
    try:
        token = get_keycloak_token(
            client_id=os.environ.get("KEYCLOAK_DIZ_CLIENT_ID"),
            url=os.environ.get("KEYCLOAK_DIZ_TOKEN_URL")
        )
        services["keycloak"] = token is not None
    except Exception as e:
        services["keycloak"] = False
        token = None

    # --- DIZ Consent ---
    try:
        if token:
            headers = {"Authorization": f"Bearer {token}"}
            r = requests.get(
                os.environ.get("DIZ_CONSENT_ENDPOINT"),
                headers=headers,
                verify="certs/diz.crt",  # hier dein Zertifikat
                timeout=5
            )
            services["DIZ"] = r.status_code == 200
        else:
            services["DIZ"] = False
    except Exception as e:
        services["DIZ"] = False

    # --- gPAS ---
    try:
        logging.error("\n\nStart testing gPAS\n\n")
        tan = generate_tan("TEST001")
        services["gPAS"] = True
    except Exception as e:
        services["gPAS"] = False

    # --- In DB speichern ---
    for service_name, status in services.items():
        entry = ServiceStatus(service_name=service_name, status=status)
        db.session.add(entry)

    db.session.commit()

    return services
