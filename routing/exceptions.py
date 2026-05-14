class RoutingError(Exception):
    """Base exception for routing domain failures."""


class LocationNotFoundError(RoutingError):
    pass


class RoutingProviderError(RoutingError):
    pass


class NoFeasibleFuelPlanError(RoutingError):
    pass
