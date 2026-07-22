# utils/tan_service.py
from zeep import Client
from zeep.transports import Transport
from zeep.exceptions import Fault
from requests import Session
import os
import logging
from utils.ca_bundle import get_ca_bundle
from utils.keycloak import get_keycloak_token
from utils.logging import log_entry_and_flash

GPAS_URL = os.environ.get("GPAS_URL")
GPAS_WSDL = os.environ.get("GPAS_WSDL")

def get_session():
    session = Session()
    proxy = os.environ.get("PROXY")
    if proxy:
        session.proxies = {"http": proxy, "https": proxy}
    session.verify = get_ca_bundle()
    session.headers.update({"Authorization": f"Bearer {get_keycloak_token(os.environ["KEYCLOAK_GPAS_CLIENT_ID"],os.environ["KEYCLOAK_GPAS_TOKEN_URL"])}"})
    return session

def generate_tan(case_id: str) -> str:
    if case_id in ("", None) or not case_id.isdigit():
        return ""
    """Generates TAN using gPAS SOAP interface."""
    if not case_id.startswith("00"):
        case_id = f"00{case_id}"
    session = get_session()
    transport = Transport(session=session)
    client = Client(GPAS_WSDL, transport=transport)
    try:
        result = client.service.getOrCreatePseudonymFor(value=case_id, domainName="arbeitsnummer")
        tan = client.service.createPseudonymFor(value=result, domainName="vorgangsnummer")
        log_entry_and_flash(case_id, "", "info", "TAN wurde generiert")
        return tan
    except Fault as e:
        log_entry_and_flash(case_id, "", "error",f"TAN konnte nicht erzeugt werden. Fehler: {e.message}")
        raise RuntimeError(f"SOAP Fault: {e}")
    except Exception as e:
        log_entry_and_flash(case_id, "", "error", f"gPAS konnte nicht aufgerufen werden. Fehler: {str(e)}")
        raise RuntimeError(f"gPAS error: {e}")
