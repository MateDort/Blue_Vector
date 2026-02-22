"""
mock_data.py — Fake current data for demos and offline testing.

Explain like you're 8:
  When we don't have real ocean data, we pretend the whole ocean is moving
  one way (or calm). That way we can still run the algorithm and compare
  "good current" vs "bad current" without needing the internet.
"""

from typing import Optional


class MockCurrentProvider:
    """
    Returns a fixed (u, v) current everywhere. No network, no files.

    Args:
        u_ms: east velocity (m/s). Positive = eastward.
        v_ms: north velocity (m/s). Positive = northward.
    """

    def __init__(self, u_ms: float = 0.0, v_ms: float = 0.0):
        self.u_ms = u_ms
        self.v_ms = v_ms

    def get_currents(self, lat: float, lon: float, time) -> tuple:
        """Returns (u, v, forecast_expired=False) — same interface as CurrentProvider."""
        return self.u_ms, self.v_ms, False

    def get_dataset(self):
        """No xarray dataset — viz will skip the quiver plot."""
        return None


# ── Preset factories ──────────────────────────────────────────────────────────

def preset_favorable_eastbound() -> MockCurrentProvider:
    """
    North Pacific-style current: strong eastward + slight northward.
    Models the Kuroshio Extension / North Pacific Current (u≈0.5, v≈0.1 m/s).
    Ideal for trans-Pacific routes (China → LA).
    """
    return MockCurrentProvider(u_ms=0.5, v_ms=0.03)


def preset_unfavorable_westbound() -> MockCurrentProvider:
    """Counter-current: westward + slight southward — fighting the vessel heading east."""
    return MockCurrentProvider(u_ms=-0.5, v_ms=-0.1)


def preset_cross() -> MockCurrentProvider:
    """Northward cross-current — perpendicular to a typical east/west route."""
    return MockCurrentProvider(u_ms=0.0, v_ms=0.5)


def preset_calm() -> MockCurrentProvider:
    """Very weak current — nearly no help or hindrance."""
    return MockCurrentProvider(u_ms=0.02, v_ms=0.01)


PRESETS = {
    "favorable": preset_favorable_eastbound,
    "unfavorable": preset_unfavorable_westbound,
    "cross": preset_cross,
    "calm": preset_calm,
}


def get_preset(name: str) -> MockCurrentProvider:
    """Look up a preset by name. Raises KeyError for unknown names."""
    if name not in PRESETS:
        raise KeyError(f"Unknown preset '{name}'. Choose from: {list(PRESETS)}")
    return PRESETS[name]()
