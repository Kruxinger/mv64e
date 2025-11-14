# utils/keycloak.py
import os
import time
import requests

_TOKEN_CACHE = {"value": None, "expires": 0}

def get_keycloak_token(client_id, url):
    """Fetch or reuse a Keycloak token with simple in-memory caching."""
    if _TOKEN_CACHE["value"] and time.time() < _TOKEN_CACHE["expires"]:
        return _TOKEN_CACHE["value"]

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

    response = requests.post(
        url,
        data=data,
        headers=headers,
        proxies=proxies,
        verify=verify,
    )
    response.raise_for_status()
    token_data = response.json()
    _TOKEN_CACHE["value"] = token_data["access_token"]
    _TOKEN_CACHE["expires"] = time.time() + token_data.get("expires_in", 300)
    return _TOKEN_CACHE["value"]
