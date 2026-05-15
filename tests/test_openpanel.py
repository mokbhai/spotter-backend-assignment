import importlib

import requests
from django.test import override_settings
from rest_framework.test import APIClient


def test_openpanel_settings_read_environment(monkeypatch):
    monkeypatch.setenv("OPENPANEL_CLIENT_ID", "client-id")
    monkeypatch.setenv("OPENPANEL_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("OPENPANEL_API_URL", "https://openpanel.example.test/api")
    monkeypatch.setenv("OPENPANEL_DISABLED", "false")

    from spotter_backend import settings as project_settings

    project_settings = importlib.reload(project_settings)

    assert project_settings.OPENPANEL_CLIENT_ID == "client-id"
    assert project_settings.OPENPANEL_CLIENT_SECRET == "client-secret"
    assert project_settings.OPENPANEL_API_URL == "https://openpanel.example.test/api"
    assert project_settings.OPENPANEL_DISABLED is False


@override_settings(
    OPENPANEL_CLIENT_ID="client-id",
    OPENPANEL_CLIENT_SECRET="client-secret",
    OPENPANEL_API_URL="https://openpanel.example.test/api",
    OPENPANEL_DISABLED=False,
)
def test_openpanel_track_posts_event_payload(monkeypatch):
    from routing.services.openpanel import track_event

    calls = []

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))

        class Response:
            status_code = 202

            def raise_for_status(self):
                return None

        return Response()

    monkeypatch.setattr(requests, "post", fake_post)

    sent = track_event(
        "backend_api_call",
        {"path": "/api/routes/fuel-plan/", "status_code": 200},
        profile_id="profile-1",
        client_ip="203.0.113.10",
        user_agent="pytest-agent",
    )

    assert sent is True
    assert calls == [
        (
            "https://openpanel.example.test/api/track",
            {
                "json": {
                    "type": "track",
                    "payload": {
                        "name": "backend_api_call",
                        "properties": {
                            "path": "/api/routes/fuel-plan/",
                            "status_code": 200,
                        },
                        "profileId": "profile-1",
                    },
                },
                "headers": {
                    "Content-Type": "application/json",
                    "openpanel-client-id": "client-id",
                    "openpanel-client-secret": "client-secret",
                    "openpanel-sdk-name": "spotter-backend",
                    "openpanel-sdk-version": "1.0.0",
                    "x-client-ip": "203.0.113.10",
                    "user-agent": "pytest-agent",
                },
                "timeout": 2,
            },
        )
    ]


@override_settings(
    OPENPANEL_CLIENT_ID="client-id",
    OPENPANEL_CLIENT_SECRET="",
    OPENPANEL_DISABLED=False,
)
def test_openpanel_track_skips_when_secret_missing(monkeypatch):
    from routing.services.openpanel import track_event

    def fail_if_called(*args, **kwargs):
        raise AssertionError("OpenPanel request should not be sent without a secret")

    monkeypatch.setattr(requests, "post", fail_if_called)

    assert track_event("backend_api_call", {}) is False


@override_settings(
    OPENPANEL_CLIENT_ID="client-id",
    OPENPANEL_CLIENT_SECRET="client-secret",
    OPENPANEL_DISABLED=True,
)
def test_openpanel_track_skips_when_disabled(monkeypatch):
    from routing.services.openpanel import track_event

    def fail_if_called(*args, **kwargs):
        raise AssertionError("OpenPanel request should not be sent when disabled")

    monkeypatch.setattr(requests, "post", fail_if_called)

    assert track_event("backend_api_call", {}) is False


@override_settings(
    OPENPANEL_CLIENT_ID="client-id",
    OPENPANEL_CLIENT_SECRET="client-secret",
    OPENPANEL_API_URL="https://openpanel.example.test/api",
    OPENPANEL_DISABLED=False,
)
def test_api_requests_are_tracked_by_middleware(monkeypatch):
    import routing.services.openpanel as openpanel

    events = []

    def fake_track_event(name, properties, **kwargs):
        events.append((name, properties, kwargs))
        return True

    monkeypatch.setattr(openpanel, "track_event", fake_track_event)

    response = APIClient().post(
        "/api/routes/fuel-plan/",
        {"start": "Austin, TX", "corridor_miles": 99},
        format="json",
        HTTP_USER_AGENT="pytest-agent",
        REMOTE_ADDR="203.0.113.20",
    )

    assert response.status_code == 400
    assert events == [
        (
            "backend_api_call",
            {
                "method": "POST",
                "path": "/api/routes/fuel-plan/",
                "status_code": 400,
                "duration_ms": events[0][1]["duration_ms"],
                "query_string": "",
            },
            {
                "client_ip": "203.0.113.20",
                "user_agent": "pytest-agent",
                "profile_id": None,
            },
        )
    ]
    assert isinstance(events[0][1]["duration_ms"], int)


@override_settings(
    OPENPANEL_CLIENT_ID="client-id",
    OPENPANEL_CLIENT_SECRET="client-secret",
    OPENPANEL_API_URL="https://openpanel.example.test/api",
    OPENPANEL_DISABLED=False,
)
def test_openpanel_config_endpoint_exposes_public_config_only():
    response = APIClient().get("/api/openpanel/config/")

    assert response.status_code == 200
    assert response.json() == {
        "clientId": "client-id",
        "apiUrl": "https://openpanel.example.test/api",
        "disabled": False,
    }
    assert "clientSecret" not in response.json()
