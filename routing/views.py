from rest_framework.response import Response
from rest_framework.views import APIView

from routing.exceptions import (
    LocationNotFoundError,
    NoFeasibleFuelPlanError,
    RoutingProviderError,
)
from routing.serializers import FuelPlanRequestSerializer
from routing.services.planner import build_route_fuel_plan


class FuelPlanView(APIView):
    authentication_classes = []
    permission_classes = []
    throttle_scope = "fuel_plan"

    def post(self, request):
        serializer = FuelPlanRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            result = build_route_fuel_plan(**serializer.validated_data)
        except LocationNotFoundError:
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
            return Response(
                {
                    "error": "no_feasible_fuel_plan",
                    "message": (
                        "A route was found, but the available fuel-price dataset "
                        "does not contain enough reachable fuel stations to complete "
                        "the trip within a 500-mile vehicle range."
                    ),
                },
                status=422,
            )
        except RoutingProviderError:
            return Response(
                {
                    "error": "routing_unavailable",
                    "message": "Route calculation is temporarily unavailable.",
                },
                status=503,
            )

        return Response(result)
