# utils/tan_service.py
from zeep import Client
from zeep.transports import Transport
from zeep.exceptions import Fault
from requests import Session
import os
from utils.keycloak import get_keycloak_token

GPAS_URL = os.environ.get("GPAS_URL")
GPAS_WSDL = os.environ.get("GPAS_WSDL")
DOMAIN_NAME = os.environ.get("GPAS_DOMAIN", "arbeitsnummer")

def get_session():
    session = Session()
    proxy = os.environ.get("PROXY")
    if proxy:
        session.proxies = {"http": proxy, "https": proxy}
    session.verify = False
    session.headers.update({"Authorization": f"Bearer {get_keycloak_token(os.environ["KEYCLOAK_GPAS_CLIENT_ID"],os.environ["KEYCLOAK_GPAS_TOKEN_URL"])}"})
    return session

def generate_tan(pat_id: str) -> str:
    """Generates TAN using gPAS SOAP interface."""
    session = get_session()
    transport = Transport(session=session)
    client = Client(GPAS_WSDL, transport=transport)
    try:
        result = client.service.getPseudonymFor(value=pat_id, domainName="arbeitssnummer")
        tan = client.service.createPseudonymFor(value=result, domainName="vorgangsnummer")
        return tan
    except Fault as e:
        raise RuntimeError(f"SOAP Fault: {e}")
    except Exception as e:
        raise RuntimeError(f"gPAS error: {e}")
