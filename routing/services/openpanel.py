import logging
from decimal import Decimal

import requests
from django.conf import settings


LOGGER = logging.getLogger(__name__)
SDK_NAME = "spotter-backend"
SDK_VERSION = "1.0.0"
REQUEST_TIMEOUT_SECONDS = 2


def is_enabled():
    return (
        not settings.OPENPANEL_DISABLED
        and bool(settings.OPENPANEL_CLIENT_ID)
        and bool(settings.OPENPANEL_CLIENT_SECRET)
    )


def public_config():
    return {
        "clientId": settings.OPENPANEL_CLIENT_ID,
        "apiUrl": settings.OPENPANEL_API_URL,
        "disabled": settings.OPENPANEL_DISABLED or not bool(settings.OPENPANEL_CLIENT_ID),
    }


def track_event(
    name,
    properties=None,
    *,
    profile_id=None,
    client_ip=None,
    user_agent=None,
):
    if not is_enabled():
        return False

    payload = {
        "type": "track",
        "payload": {
            "name": name,
            "properties": _json_safe(properties or {}),
            "profileId": profile_id,
        },
    }
    headers = {
        "Content-Type": "application/json",
        "openpanel-client-id": settings.OPENPANEL_CLIENT_ID,
        "openpanel-client-secret": settings.OPENPANEL_CLIENT_SECRET,
        "openpanel-sdk-name": SDK_NAME,
        "openpanel-sdk-version": SDK_VERSION,
    }
    if client_ip:
        headers["x-client-ip"] = client_ip
    if user_agent:
        headers["user-agent"] = user_agent

    try:
        response = requests.post(
            f"{settings.OPENPANEL_API_URL}/track",
            json=payload,
            headers=headers,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.RequestException:
        LOGGER.exception("Failed to send OpenPanel event %s", name)
        return False

    return True


def _json_safe(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value
