"""
vessel_model.py — Physics of one simulation step plus geometry helpers.

Explain like you're 8:
  This file is the "rulebook for one move". Every 6 hours the boat is:
    1. Carried by the ocean current (free ride)
    2. Pushed a little by the sail (free if wind is blowing the right way)
    3. Pushed by the motor to steer (costs energy)
  We also measure "is the current helping or hurting?" and how far we are from the goal.
"""

import math
from blue_vector_claude.config import (
    DT_SECONDS, MAX_STEERING_SPEED_MS, SAIL_EFFICIENCY,
    EARTH_RADIUS_M,
)


# ── Main step ─────────────────────────────────────────────────────────────────

def step(
    lat: float,
    lon: float,
    u_ms: float,          # ocean current east component (m/s)
    v_ms: float,          # ocean current north component (m/s)
    steering_angle_deg: float,  # math angle: 0=East, 90=North (not compass bearing)
    u_wind_ms: float = 0.0,
    v_wind_ms: float = 0.0,
    sail_efficiency: float = SAIL_EFFICIENCY,
    sail_motor_ok: bool = True,
    propeller_motor_ok: bool = True,
    turning_motors_working: int = 2,   # 0, 1, or 2
) -> tuple:
    """
    Advance vessel position by one timestep (DT_SECONDS).

    Returns:
        (new_lat, new_lon, dx_steer, dy_steer, energy_step, dx_sail, dy_sail)
        - dx_steer / dy_steer: east/north motor displacement (m)
        - energy_step: propulsion energy this step (m²/s² × s = m²/s)
        - dx_sail / dy_sail: east/north sail displacement (m)
    """
    # ── Current ─────────────────────────────────────────────────────────────
    dx_current = u_ms * DT_SECONDS
    dy_current = v_ms * DT_SECONDS

    # ── Sail ─────────────────────────────────────────────────────────────────
    if sail_motor_ok:
        dx_sail = sail_efficiency * u_wind_ms * DT_SECONDS
        dy_sail = sail_efficiency * v_wind_ms * DT_SECONDS
    else:
        dx_sail = 0.0
        dy_sail = 0.0

    # ── Steering (motor) ─────────────────────────────────────────────────────
    if propeller_motor_ok and turning_motors_working > 0:
        # Each turning motor contributes half of max speed
        mag = (turning_motors_working / 2) * MAX_STEERING_SPEED_MS
        angle_rad = math.radians(steering_angle_deg)
        dx_steer = mag * math.cos(angle_rad) * DT_SECONDS
        dy_steer = mag * math.sin(angle_rad) * DT_SECONDS
    else:
        dx_steer = 0.0
        dy_steer = 0.0

    # ── Total displacement ───────────────────────────────────────────────────
    dx_tot = dx_current + dx_sail + dx_steer
    dy_tot = dy_current + dy_sail + dy_steer

    # ── Meters → lat/lon degrees ─────────────────────────────────────────────
    # 1° latitude ≈ 111 320 m (constant)
    # 1° longitude ≈ 111 320 × cos(lat) m (shorter near poles)
    m_per_deg_lat = 111_320.0
    m_per_deg_lon = 111_320.0 * math.cos(math.radians(lat))

    new_lat = lat + dy_tot / m_per_deg_lat
    new_lon = lon + dx_tot / m_per_deg_lon

    # ── Propulsion energy ────────────────────────────────────────────────────
    # v_steer = |steering displacement| / time
    # energy = v_steer² × time  (quadratic in speed, like aerodynamic drag power)
    v_steer = math.sqrt(dx_steer ** 2 + dy_steer ** 2) / DT_SECONDS
    energy_step = v_steer ** 2 * DT_SECONDS

    return new_lat, new_lon, dx_steer, dy_steer, energy_step, dx_sail, dy_sail


# ── Geometry helpers ──────────────────────────────────────────────────────────

def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Compass bearing from (lat1,lon1) to (lat2,lon2) in degrees.
    0° = North, 90° = East, 180° = South, 270° = West.
    """
    φ1 = math.radians(lat1)
    φ2 = math.radians(lat2)
    Δλ = math.radians(lon2 - lon1)

    x = math.sin(Δλ) * math.cos(φ2)
    y = math.cos(φ1) * math.sin(φ2) - math.sin(φ1) * math.cos(φ2) * math.cos(Δλ)

    bearing = math.degrees(math.atan2(x, y))
    return bearing % 360.0


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine distance in kilometres."""
    φ1, φ2 = math.radians(lat1), math.radians(lat2)
    Δφ = math.radians(lat2 - lat1)
    Δλ = math.radians(lon2 - lon1)

    a = math.sin(Δφ / 2) ** 2 + math.cos(φ1) * math.cos(φ2) * math.sin(Δλ / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return EARTH_RADIUS_M * c / 1000.0


def current_favorability(
    lat: float, lon: float,
    target_lat: float, target_lon: float,
    u: float, v: float,
) -> float:
    """
    How much does the current push us toward the target?

    Returns a value in [-1, 1]:
      +1 = current points exactly toward target
       0 = current is perpendicular (neither help nor harm)
      -1 = current points exactly away from target
    """
    b = math.radians(bearing_deg(lat, lon, target_lat, target_lon))
    # Unit vector toward target in (east, north) frame
    ex = math.sin(b)   # east component
    ey = math.cos(b)   # north component

    speed = math.sqrt(u ** 2 + v ** 2) + 1e-9  # avoid division by zero
    return (u * ex + v * ey) / speed


def straight_line_energy(dist_km: float, speed_ms: float = MAX_STEERING_SPEED_MS) -> tuple:
    """
    Energy cost of travelling dist_km in a straight line at constant speed_ms.

    Returns:
        (time_seconds, energy)
        energy = speed_ms² × time_s  (same units as energy_step in step())
    """
    dist_m = dist_km * 1000.0
    time_s = dist_m / max(speed_ms, 1e-9)
    energy = speed_ms ** 2 * time_s
    return time_s, energy


def bearing_to_math_angle(bearing: float) -> float:
    """
    Convert compass bearing (0=N, clockwise) to math angle (0=E, counter-clockwise).
    Used when converting bearing into cos/sin steering components.
    """
    return (90.0 - bearing) % 360.0
