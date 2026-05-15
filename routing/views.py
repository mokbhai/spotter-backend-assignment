from rest_framework.response import Response
from rest_framework.views import APIView

from routing.exceptions import (
    LocationNotFoundError,
    NoFeasibleFuelPlanError,
    RoutingProviderError,
)
from routing.serializers import FuelPlanRequestSerializer
from routing.services import openpanel
from routing.services.planner import build_route_fuel_plan


class OpenPanelConfigView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        return Response(openpanel.public_config())


class FuelPlanView(APIView):
    authentication_classes = []
    permission_classes = []
    throttle_scope = "fuel_plan"

    def post(self, request):
        serializer = FuelPlanRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self._corridor_miles = serializer.validated_data["corridor_miles"]

        try:
            result = build_route_fuel_plan(**serializer.validated_data)
        except LocationNotFoundError:
            self._track_plan_event(request, "location_not_found")
            return Response(
                {
                    "error": "location_not_found",
                    "message": (
                        "Start or destination could not be resolved to a USA location."
                    ),
                },
                status=422,
            )
        except NoFeasibleFuelPlanError:
            max_range_miles = serializer.validated_data["max_range_miles"]
            self._track_plan_event(
                request,
                "no_feasible_fuel_plan",
                {"max_range_miles": max_range_miles},
            )
            return Response(
                {
                    "error": "no_feasible_fuel_plan",
                    "message": (
                        "A route was found, but the available fuel-price dataset "
                        "does not contain enough reachable fuel stations to complete "
                        f"the trip within a {max_range_miles}-mile vehicle range."
                    ),
                },
                status=422,
            )
        except RoutingProviderError:
            self._track_plan_event(request, "routing_unavailable")
            return Response(
                {
                    "error": "routing_unavailable",
                    "message": "Route calculation is temporarily unavailable.",
                },
                status=503,
            )

        fuel_plan = result.get("fuel_plan", {})
        route = result.get("route", {})
        self._track_plan_event(
            request,
            "success",
            {
                "distance_miles": route.get("distance_miles"),
                "total_cost": fuel_plan.get("total_cost"),
                "stops_count": len(fuel_plan.get("stops", [])),
            },
        )
        return Response(result)

    def _track_plan_event(self, request, outcome, extra_properties=None):
        properties = {
            "outcome": outcome,
            "corridor_miles": getattr(self, "_corridor_miles", None),
        }
        properties.update(extra_properties or {})
        openpanel.track_event(
            "fuel_plan_request",
            properties,
            profile_id=request.headers.get("X-OpenPanel-Profile-Id"),
            client_ip=_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT"),
        )


def _client_ip(request):
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()
    return request.META.get("REMOTE_ADDR")
