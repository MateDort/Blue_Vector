"""
Vessel model: position(t+1) = position(t) + current + sail + steering.
4 motors: 1 sail (powers sail), 1 propeller (drives prop), 2 turning (steering).
Steering magnitude: 0 if propeller or both turning motors failed; else (turning_working/2)*max_speed.
Sail displacement only when sail motor ok. Energy ∝ |steering_vector|² × time.
"""
import math
from typing import Tuple, Optional

from config import (
    TIMESTEP_HOURS,
    MAX_STEERING_SPEED_MS,
    EARTH_RADIUS_M,
)

# Seconds per 6-hour step
DT_SECONDS = TIMESTEP_HOURS * 3600


def _meters_to_lat_lon(dx_m: float, dy_m: float, lat: float) -> Tuple[float, float]:
    """
    Convert displacement in meters (east, north) to delta_lat, delta_lon in degrees.
    Spherical approximation: 1 deg lat ≈ 111320 m; 1 deg lon ≈ 111320*cos(lat) m.
    """
    m_per_deg_lat = 111320.0
    m_per_deg_lon = 111320.0 * max(0.01, math.cos(math.radians(lat)))
    dlat = dy_m / m_per_deg_lat
    dlon = dx_m / m_per_deg_lon
    return (dlat, dlon)


def _lat_lon_to_meters(dlat: float, dlon: float, lat: float) -> Tuple[float, float]:
    """Convert delta_lat, delta_lon (degrees) to meters (east, north)."""
    m_per_deg_lat = 111320.0
    m_per_deg_lon = 111320.0 * max(0.01, math.cos(math.radians(lat)))
    dx_m = dlon * m_per_deg_lon
    dy_m = dlat * m_per_deg_lat
    return (dx_m, dy_m)


def _steering_speed_ms(
    propeller_motor_ok: bool,
    turning_motors_working: int,
    steering_magnitude_ms: float = MAX_STEERING_SPEED_MS,
) -> float:
    """Effective steering speed: 0 if propeller or no turning motors; else (turning/2)*max."""
    if not propeller_motor_ok or turning_motors_working <= 0:
        return 0.0
    cap = (turning_motors_working / 2.0) * MAX_STEERING_SPEED_MS
    return min(steering_magnitude_ms, cap)


def step(
    lat: float,
    lon: float,
    u_ms: float,
    v_ms: float,
    steering_angle_deg: float,
    steering_magnitude_ms: float = MAX_STEERING_SPEED_MS,
    u_wind_ms: Optional[float] = None,
    v_wind_ms: Optional[float] = None,
    sail_efficiency: float = 0.0,
    motor_available: bool = True,
    *,
    sail_motor_ok: Optional[bool] = None,
    propeller_motor_ok: Optional[bool] = None,
    turning_motors_working: Optional[int] = None,
) -> Tuple[float, float, float, float, float, float, float]:
    """
    Advance vessel one timestep.
    4 motors: sail (sail_motor_ok), propeller (propeller_motor_ok), 2 turning (turning_motors_working 0/1/2).
    If sail_motor_ok/propeller_motor_ok/turning_motors_working are not passed, motor_available is used
    for steering (backward compatible): steering = motor_available ? full : 0, sail = motor_available.
    """
    # Resolve 4-motor vs legacy motor_available
    sail_ok = sail_motor_ok if sail_motor_ok is not None else motor_available
    prop_ok = propeller_motor_ok if propeller_motor_ok is not None else motor_available
    turn_n = turning_motors_working if turning_motors_working is not None else (2 if motor_available else 0)

    # Current displacement over timestep (m)
    dx_current = u_ms * DT_SECONDS
    dy_current = v_ms * DT_SECONDS

    # Sail: only when sail motor ok
    dx_sail, dy_sail = 0.0, 0.0
    if sail_ok and sail_efficiency > 0 and u_wind_ms is not None and v_wind_ms is not None:
        dx_sail = sail_efficiency * u_wind_ms * DT_SECONDS
        dy_sail = sail_efficiency * v_wind_ms * DT_SECONDS

    # Steering: propeller + turning motors (0, 1, or 2 working → 0, half, full speed)
    mag = _steering_speed_ms(prop_ok, turn_n, steering_magnitude_ms)
    rad = math.radians(steering_angle_deg)
    dx_steer = mag * math.cos(rad) * DT_SECONDS
    dy_steer = mag * math.sin(rad) * DT_SECONDS

    # Total displacement in meters
    dx_tot = dx_current + dx_sail + dx_steer
    dy_tot = dy_current + dy_sail + dy_steer

    dlat, dlon = _meters_to_lat_lon(dx_tot, dy_tot, lat)
    new_lat = lat + dlat
    new_lon = lon + dlon

    # Propulsion energy only when motor used
    steering_speed_ms = math.sqrt(dx_steer**2 + dy_steer**2) / DT_SECONDS
    propulsion_energy_step = (steering_speed_ms ** 2) * DT_SECONDS

    return (new_lat, new_lon, dx_steer, dy_steer, propulsion_energy_step, dx_sail, dy_sail)


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Bearing from (lat1,lon1) to (lat2,lon2) in degrees (0 = north, 90 = east)."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dlam = math.radians(lon2 - lon1)
    x = math.sin(dlam) * math.cos(phi2)
    y = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlam)
    theta = math.degrees(math.atan2(x, y))
    return (theta + 360) % 360


def current_favorability(
    lat: float,
    lon: float,
    target_lat: float,
    target_lon: float,
    u_ms: float,
    v_ms: float,
) -> float:
    """
    How much the current (u, v) in m/s (east, north) takes us toward the target.
    Returns value in [-1, 1]: 1 = current straight toward target, -1 = straight away, 0 = perpendicular.
    Used to decide if we're in a "good" or "bad" current and when to use propeller to change lane.
    """
    b = bearing_deg(lat, lon, target_lat, target_lon)
    # Unit vector toward target: east = sin(b), north = cos(b) (bearing 0=north, 90=east)
    ex = math.sin(math.radians(b))
    ey = math.cos(math.radians(b))
    speed = math.sqrt(u_ms * u_ms + v_ms * v_ms) + 1e-9
    # Component of current toward target (normalized by speed so result in [-1,1])
    return float((u_ms * ex + v_ms * ey) / speed)


def is_current_favorable(
    favorability: float,
    threshold: float = 0.0,
) -> bool:
    """True if current is taking us toward target (favorability > threshold)."""
    return favorability > threshold


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine distance in km."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return EARTH_RADIUS_M * c / 1000.0


def straight_line_energy_km(
    dist_km: float, speed_ms: float = MAX_STEERING_SPEED_MS
) -> Tuple[float, float]:
    """
    Baseline: straight-line propulsion at constant speed.
    Returns (time_seconds, propulsion_energy) for that segment.
    Energy ∝ speed² * time, time = distance / speed.
    """
    if speed_ms <= 0:
        return (0.0, 0.0)
    distance_m = dist_km * 1000.0
    time_seconds = distance_m / speed_ms
    energy = (speed_ms ** 2) * time_seconds
    return (time_seconds, energy)
