"""
config.py — All tuneable constants for Blue Vector.

Explain like you're 8:
  This file is the "rules of the game". Everything else imports from here.
  Change a number here and the whole simulation changes.
"""

# ── Time ──────────────────────────────────────────────────────────────────────
TIMESTEP_HOURS: int = 6              # hours per simulation step
DT_SECONDS: int = TIMESTEP_HOURS * 3600  # 21 600 s — used everywhere in physics

# ── Vessel ────────────────────────────────────────────────────────────────────
MAX_STEERING_SPEED_MS: float = 0.3   # max motor steering speed (m/s)
SAIL_EFFICIENCY: float = 0.35        # fraction of wind speed converted to movement

# ── Horizon (look-ahead for receding-horizon optimiser) ───────────────────────
HORIZON_DAYS: int = 5
HORIZON_STEPS: int = HORIZON_DAYS * (24 // TIMESTEP_HOURS)  # 20 steps

# ── Steering search ───────────────────────────────────────────────────────────
ANGLE_RANGE_DEG: float = 45.0        # sample ±45° around bearing
ANGLE_STEP_DEG: float = 5.0          # resolution of candidate angles
FORECAST_EXPIRED_ANGLE_RANGE_DEG: float = 15.0  # narrower when data is stale

# ── Cost weights ──────────────────────────────────────────────────────────────
ALPHA: float = 1.0   # weight on time (days) in cost
BETA: float = 1.0    # weight on remaining distance (km) in cost
BAD_CURRENT_PENALTY_WEIGHT: float = 0.5
PROPELLER_SAVE_IN_GOOD_CURRENT_WEIGHT: float = 0.0
# NOTE: Setting this to 0 lets the motor steer freely toward the target even in
# good currents.  The energy benefit of exploiting currents is implicit — the
# current provides free velocity so the motor works less per km regardless.
EMERGENCY_TIME_ONLY_ALPHA: float = 20.0  # heavy time weight in emergency mode

# ── Geometry ──────────────────────────────────────────────────────────────────
EARTH_RADIUS_M: float = 6_371_000.0
DISTANCE_TOLERANCE_KM: float = 50.0  # "arrived" if within this distance
# NOTE: With 6-hour timesteps and realistic sail+current speeds (~2 m/s),
# each step covers 40–55 km.  Tolerance must be >= step distance to reliably
# detect arrival. 50 km is appropriate for trans-oceanic long-range routing.

# ── Data / caching ────────────────────────────────────────────────────────────
# (lat_min, lon_min, lat_max, lon_max)
DEFAULT_BBOX: tuple = (25.0, -80.0, 45.0, -60.0)
NETCDF_CACHE_PATH: str = "data/currents_cache.nc"
CACHE_MAX_AGE_HOURS: float = 12.0    # re-download if older than this
