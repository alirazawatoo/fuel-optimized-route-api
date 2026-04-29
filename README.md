# Route and fuel-cost API

The Django application is in [map_API](map_API/). It requests an OpenRouteService driving route, samples nearby station prices from PostgreSQL, and estimates fuel consumption.

Read the [setup, request example, and algorithm limits](map_API/README.md) before using it. This is an exploratory heuristic, not a navigation service or a globally optimal refueling plan.
