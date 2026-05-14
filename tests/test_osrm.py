from decimal import Decimal

import pytest
import requests

from routing.exceptions import RoutingProviderError
from routing.services.osrm import OSRMClient


class FakeResponse:
    def __init__(self, payload=None, status_error=None, json_error=None):
        self.payload = payload
        self.status_error = status_error
        self.json_error = json_error

    def raise_for_status(self):
        if self.status_error:
            raise self.status_error

    def json(self):
        if self.json_error:
            raise self.json_error
        return self.payload


def test_osrm_client_normalizes_route(monkeypatch):
    calls = []
    geometry = {
        "type": "LineString",
        "coordinates": [[-97.7431, 30.2672], [-95.3698, 29.7604]],
    }

    def fake_get(url, params, timeout):
        calls.append((url, params, timeout))
        return FakeResponse(
            {
                "code": "Ok",
                "routes": [
                    {
                        "distance": 1609.344,
                        "geometry": geometry,
                    }
                ],
            }
        )

    monkeypatch.setattr("routing.services.osrm.requests.get", fake_get)

    route = OSRMClient(base_url="https://osrm.example.test/", timeout=3).route(
        Decimal("30.2672"),
        Decimal("-97.7431"),
        Decimal("29.7604"),
        Decimal("-95.3698"),
    )

    assert route.distance_miles == pytest.approx(1.0)
    assert route.geometry == geometry
    assert calls == [
        (
            "https://osrm.example.test/route/v1/driving/-97.7431,30.2672;-95.3698,29.7604",
            {
                "overview": "full",
                "geometries": "geojson",
                "steps": "false",
            },
            3,
        )
    ]


def test_osrm_client_raises_provider_error_for_no_route(monkeypatch):
    monkeypatch.setattr(
        "routing.services.osrm.requests.get",
        lambda *args, **kwargs: FakeResponse({"code": "NoRoute", "routes": []}),
    )

    with pytest.raises(RoutingProviderError):
        OSRMClient(base_url="https://osrm.example.test").route(
            Decimal("30.2672"),
            Decimal("-97.7431"),
            Decimal("29.7604"),
            Decimal("-95.3698"),
        )


def test_osrm_client_maps_http_failure_to_provider_error(monkeypatch):
    monkeypatch.setattr(
        "routing.services.osrm.requests.get",
        lambda *args, **kwargs: FakeResponse(
            status_error=requests.HTTPError("bad gateway")
        ),
    )

    with pytest.raises(RoutingProviderError):
        OSRMClient(base_url="https://osrm.example.test").route(
            Decimal("30.2672"),
            Decimal("-97.7431"),
            Decimal("29.7604"),
            Decimal("-95.3698"),
        )


def test_osrm_client_maps_malformed_protocol_payload_to_provider_error(monkeypatch):
    monkeypatch.setattr(
        "routing.services.osrm.requests.get",
        lambda *args, **kwargs: FakeResponse(["not", "an", "object"]),
    )

    with pytest.raises(RoutingProviderError):
        OSRMClient(base_url="https://osrm.example.test").route(
            Decimal("30.2672"),
            Decimal("-97.7431"),
            Decimal("29.7604"),
            Decimal("-95.3698"),
        )


@pytest.mark.parametrize(
    "geometry",
    [
        None,
        {},
        {"type": "Point", "coordinates": [-97.7431, 30.2672]},
        {"type": "LineString", "coordinates": []},
        {"type": "LineString", "coordinates": "not-coordinates"},
    ],
)
def test_osrm_client_rejects_malformed_geometry(monkeypatch, geometry):
    monkeypatch.setattr(
        "routing.services.osrm.requests.get",
        lambda *args, **kwargs: FakeResponse(
            {
                "code": "Ok",
                "routes": [
                    {
                        "distance": 1609.344,
                        "geometry": geometry,
                    }
                ],
            }
        ),
    )

    with pytest.raises(RoutingProviderError):
        OSRMClient(base_url="https://osrm.example.test").route(
            Decimal("30.2672"),
            Decimal("-97.7431"),
            Decimal("29.7604"),
            Decimal("-95.3698"),
        )
