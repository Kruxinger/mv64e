# utils/keycloak.py
import logging
import os
import time
import requests

from utils.logging import log_entry


def get_keycloak_token(client_id, url):


    data = {
        "client_id": client_id,
        "client_secret": os.environ["KEYCLOAK_CLIENT_SECRET"],
        "username": os.environ["KEYCLOAK_USERNAME"],
        "password": os.environ["KEYCLOAK_PASSWORD"],
        "grant_type": "password",
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    proxies = {"http": os.getenv("PROXY", ""), "https": os.getenv("PROXY", "")}
    verify = False
    try:
        response = requests.post(
            url,
            data=data,
            headers=headers,
            proxies=proxies,
            verify=verify,
        )
        response.raise_for_status()
        token_data = response.json()
        return token_data["access_token"]
    except Exception as e:
        log_entry("", "", "error", f"Could not load KeyCloak token: {str(e)}")

