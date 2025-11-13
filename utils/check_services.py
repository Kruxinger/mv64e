import os
import requests
from models import db, ServiceStatus  # SQLAlchemy Models

def check_services():
    """
    Prüft externe Services und speichert den Status in der DB.
    Läuft innerhalb eines Flask App Context.
    """
    services = {}

    # --- Keycloak ---
    try:
        r = requests.post(
            os.environ.get("KEYCLOAK_TOKEN_URL"),
            data={
                "grant_type": "password",
                "client_id": os.environ.get("KEYCLOAK_CLIENT_ID"),
                "client_secret": os.environ.get("KEYCLOAK_CLIENT_SECRET"),
                "username": os.environ.get("KEYCLOAK_USERNAME"),
                "password": os.environ.get("KEYCLOAK_PASSWORD")
            },
            timeout=5
        )
        services["keycloak"] = r.status_code == 200
    except Exception:
        services["keycloak"] = False

    # --- DIZ Consent ---
    try:
        r = requests.get(os.environ.get("DIZ_CONSENT_ENDPOINT"), timeout=5)
        services["DIZ"] = r.status_code == 200
    except Exception:
        services["DIZ"] = False

    # --- gPAS ---
    try:
        r = requests.get(os.environ.get("GPAS_URL"), timeout=5)
        services["gPAS"] = r.status_code == 200
    except Exception:
        services["gPAS"] = False

    # --- In DB speichern ---
    for service_name, status in services.items():
        entry = ServiceStatus(service_name=service_name, status=status)
        db.session.add(entry)

    db.session.commit()

    return services
