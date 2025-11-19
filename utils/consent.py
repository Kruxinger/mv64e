# utils/consent.py
import os
from requests import Session
from utils.keycloak import get_keycloak_token
from utils.logging import log_entry


def get_session():
    session = Session()
    proxy = os.environ.get("PROXY")
    if proxy:
        session.proxies = {"http": proxy, "https": proxy}
    session.verify = "certs/diz.crt"
    return session

def get_research_consent(pat_id: str):
    token = get_keycloak_token(os.environ["KEYCLOAK_DIZ_CLIENT_ID"], os.environ["KEYCLOAK_DIZ_TOKEN_URL"])
    url = f"{os.environ["DIZ_CONSENT_ENDPOINT"]}{pat_id}"
    try:
        session = get_session()
        headers = {"Authorization": f"Bearer {token}"}
        response = session.get(url, headers=headers)
        response.raise_for_status()
        log_entry("", "pat_id", "info", "Received Broad Consent from DIZ")
        return response.json()
    except Exception as e:
        log_entry("", "pat_id", "error", f"Error while requesting Broad Consent: {str(e)}")
