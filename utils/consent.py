# utils/consent.py
import os
from requests import Session
from utils.keycloak import get_keycloak_token

def get_session():
    session = Session()
    proxy = os.environ.get("PROXY")
    if proxy:
        session.proxies = {"http": proxy, "https": proxy}
    session.verify = False
    return session

def get_research_consent(patid: str):
    token = get_keycloak_token(os.environ["KEYCLOAK_DIZ_CLIENT_ID"])
    url = f"{os.environ["DIZ_CONSENT_ENDPOINT"]}{patid}"
    session = get_session()
    headers = {"Authorization": f"Bearer {token}"}
    response = session.get(url, headers=headers)
    response.raise_for_status()
    return response.json()
