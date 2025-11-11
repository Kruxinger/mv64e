import os
from requests import Session
import requests

TOKEN_FILE = "/tmp/consent_token"

def get_session():
    session = Session()
    proxy = os.environ.get("PROXY")
    if proxy:
        session.proxies = {'http': proxy, 'https': proxy}
    session.verify = False
    return session

def get_keycloak_token():
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "r") as f:
            return f.read()
    data = {
        'client_id': os.environ['KEYCLOAK_CLIENT_ID'],
        'client_secret': os.environ['KEYCLOAK_CLIENT_SECRET'],
        'username': os.environ['KEYCLOAK_USERNAME'],
        'password': os.environ['KEYCLOAK_PASSWORD'],
        'grant_type': 'password'
    }
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    session = get_session()
    response = session.post(os.environ['KEYCLOAK_TOKEN_URL'], data=data, headers=headers)
    response.raise_for_status()
    token = response.json()['access_token']
    with open(TOKEN_FILE, "w+") as f:
        f.write(token)
    return token

def get_research_consent(patid: str):
    token = get_keycloak_token()
    url = f"https://bc.diz.med.uni-muenchen.de/fhir/Consent?patient={patid}"
    session = get_session()
    headers = {'Authorization': f'Bearer {token}'}
    response = session.get(url, headers=headers)
    response.raise_for_status()
    return response.json()
