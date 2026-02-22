"""
wind_model.py — Parametric wind model (no external API).

Explain like you're 8:
  Wind follows a fixed pattern on the map:
    - Near the equator it blows WEST (trade winds).
    - In the middle latitudes it blows EAST, stronger in winter.
  This file has no grid; it's just "at this latitude and month, wind is this speed."
"""

import math
from datetime import datetime


# ── Wind speed constants (m/s) ────────────────────────────────────────────────
_TRADE_U = -4.0     # westward trade wind (east component is negative)
_WEST_U_WINTER = 5.0   # eastward westerlies in winter (Oct–Mar)
_WEST_U_SUMMER = 2.0   # eastward westerlies in summer (Jun–Aug)
_HIGH_U_WINTER = 2.0   # high-latitude winds, winter
_HIGH_U_SUMMER = 0.5   # high-latitude winds, summer

# Latitude thresholds
_TRADE_MAX_LAT = 27.0       # trade winds below this latitude
_WEST_MIN_LAT = 30.0        # westerlies start above this latitude
_WEST_MAX_LAT = 45.0        # westerlies peak zone ends here

_WINTER_MONTHS = {10, 11, 12, 1, 2, 3}  # Oct–Mar


def _is_winter(month: int) -> bool:
    return month in _WINTER_MONTHS


def get_wind(lat: float, lon: float, time: datetime) -> tuple:
    """
    Parametric wind at (lat, lon) at the given datetime.

    Returns:
        (u_wind, v_wind) in m/s
          u_wind > 0 = eastward, v_wind > 0 = northward.

    Zones:
        lat < 27°         — trade winds (westward, constant)
        27°–30°           — transition (linear blend)
        30°–45°           — westerlies (stronger in winter)
        > 45°             — high-latitude winds (weaker)
    """
    month = time.month if isinstance(time, datetime) else 1
    winter = _is_winter(month)

    westerly_u = _WEST_U_WINTER if winter else _WEST_U_SUMMER
    high_u = _HIGH_U_WINTER if winter else _HIGH_U_SUMMER

    if lat < _TRADE_MAX_LAT:
        # Pure trade wind zone
        u = _TRADE_U
    elif lat < _WEST_MIN_LAT:
        # Transition band: linear blend
        t = (lat - _TRADE_MAX_LAT) / (_WEST_MIN_LAT - _TRADE_MAX_LAT)
        u = (1 - t) * _TRADE_U + t * westerly_u
    elif lat <= _WEST_MAX_LAT:
        # Westerlies
        u = westerly_u
    else:
        # High latitudes
        u = high_u

    v = 0.0  # simplified: no persistent north/south component
    return u, v
