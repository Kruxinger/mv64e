import logging
import os

import requests
from models import db, ServiceStatus  # SQLAlchemy Models
from utils.ca_bundle import get_ca_bundle
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
                verify=get_ca_bundle(),
                timeout=5
            )
            services["DIZ"] = r.status_code == 200
        else:
            services["DIZ"] = False
    except Exception as e:
        services["DIZ"] = False

    # --- gPAS ---
    try:
        test_case_id = os.environ.get("GPAS_HEALTHCHECK_CASE_ID", "000000001")
        tan = generate_tan(test_case_id)
        services["gPAS"] = bool(tan)
    except Exception as e:
        services["gPAS"] = False

    # --- In DB speichern ---
    for service_name, status in services.items():
        entry = ServiceStatus(service_name=service_name, status=status)
        db.session.add(entry)

    db.session.commit()

    return services
