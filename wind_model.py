"""
Parametric wind model by latitude and season (month).
Westerlies 30-45°N (west→east), trade winds <27°N (east→west).
Used for sail-assisted routing and sail-only fallback when motor fails.
"""
from datetime import datetime
from typing import Tuple

# Latitude bands (degrees)
TRADE_WIND_LAT_MAX = 27.0   # below this: trade winds (east→west)
WESTERLY_LAT_MIN = 30.0     # westerlies band
WESTERLY_LAT_MAX = 45.0
# Nominal speeds m/s (east positive, north positive)
TRADE_WIND_U_MS = -4.0      # westward
WESTERLY_U_WINTER_MS = 8.0  # eastward in Nov-Mar
WESTERLY_U_SUMMER_MS = 3.0  # weaker Jun-Aug


def get_wind(lat: float, lon: float, time: datetime) -> Tuple[float, float]:
    """
    Return (u_wind, v_wind) in m/s (east, north) at (lat, lon, time).
    Parametric: trade winds south of TRADE_WIND_LAT_MAX, westerlies 30-45°N,
    scaled by month (winter stronger).
    """
    month = time.month
    # Winter months (Nov, Dec, Jan, Feb, Mar) = stronger westerlies
    is_winter = month in (11, 12, 1, 2, 3)
    if lat < TRADE_WIND_LAT_MAX:
        u = TRADE_WIND_U_MS
        v = 0.0
    elif WESTERLY_LAT_MIN <= lat <= WESTERLY_LAT_MAX:
        u = WESTERLY_U_WINTER_MS if is_winter else WESTERLY_U_SUMMER_MS
        v = 0.0
    elif lat < WESTERLY_LAT_MIN:
        # Transition 27-30: blend
        t = (lat - TRADE_WIND_LAT_MAX) / (WESTERLY_LAT_MIN - TRADE_WIND_LAT_MAX)
        u_w = WESTERLY_U_WINTER_MS if is_winter else WESTERLY_U_SUMMER_MS
        u = (1 - t) * TRADE_WIND_U_MS + t * u_w
        v = 0.0
    else:
        # Above 45: weaker, variable
        u = 2.0 if is_winter else 0.5
        v = 0.0
    return (float(u), float(v))
