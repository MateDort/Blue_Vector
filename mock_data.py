"""
Mock current (and optional wind) providers for demos and API.
Algorithm is unchanged; only the data source is mocked so the frontend can try
"favorable current" vs "unfavorable current" scenarios.
"""
from datetime import datetime
from typing import Tuple, List, Optional, Any
import math


class MockCurrentProvider:
    """
    Provides get_currents(lat, lon, time) from constant (u,v) or a simple grid.
    No NetCDF; used for API and demos.
    """

    def __init__(
        self,
        u_ms: float = 0.0,
        v_ms: float = 0.0,
        grid: Optional[List[dict]] = None,
    ):
        """
        u_ms, v_ms: constant current (east, north) in m/s when grid is None.
        grid: optional list of {"lat", "lon", "u", "v"} for nearest-neighbor lookup.
        """
        self._u = u_ms
        self._v = v_ms
        self._grid = grid or []

    def get_currents(
        self, lat: float, lon: float, time: datetime
    ) -> Tuple[float, float, bool]:
        if not self._grid:
            return (self._u, self._v, False)
        # Nearest point in grid
        best = None
        best_d = 1e30
        for p in self._grid:
            d = (p["lat"] - lat) ** 2 + (p["lon"] - lon) ** 2
            if d < best_d:
                best_d = d
                best = p
        if best is None:
            return (self._u, self._v, False)
        return (float(best["u"]), float(best["v"]), False)

    def get_dataset(self) -> Any:
        return None

    @property
    def time_range(self) -> Tuple[Optional[datetime], Optional[datetime]]:
        return (None, None)


# Preset scenarios for the web app: "favorable" = current toward target, "unfavorable" = against
def preset_favorable_eastbound() -> MockCurrentProvider:
    """Eastbound (e.g. China->LA): current and wind eastward."""
    return MockCurrentProvider(u_ms=0.15, v_ms=0.02)


def preset_unfavorable_westbound() -> MockCurrentProvider:
    """Eastbound route but current westward (fighting)."""
    return MockCurrentProvider(u_ms=-0.12, v_ms=-0.01)


def preset_cross_current() -> MockCurrentProvider:
    """Current perpendicular (northward)."""
    return MockCurrentProvider(u_ms=0.0, v_ms=0.08)


def preset_calm() -> MockCurrentProvider:
    """Very weak current."""
    return MockCurrentProvider(u_ms=0.02, v_ms=0.01)
