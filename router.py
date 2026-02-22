"""
Receding-horizon router: at each step sample steering/course directions, simulate forward,
minimize cost. The algorithm knows which current is good (toward target) vs bad, when the
current will change to bad, and when to use the propeller to change current—propeller is
only for moving between currents and for emergency-to-shore.
"""
import logging
from datetime import datetime, timedelta
from typing import Callable, Tuple, Optional

from config import (
    TIMESTEP_HOURS,
    HORIZON_DAYS,
    ANGLE_RANGE_DEG,
    ANGLE_STEP_DEG,
    ALPHA,
    BETA,
    DISTANCE_TOLERANCE_KM,
    FORECAST_EXPIRED_ANGLE_RANGE_DEG,
    MOTOR_AVAILABLE,
    WIND_AVAILABLE,
    SAIL_EFFICIENCY,
    SOUTH_LAT_LIMIT_DEG,
    LATITUDE_PENALTY_WEIGHT,
    CURRENT_FAVORABILITY_BAD_THRESHOLD,
    PROPELLER_SAVE_IN_GOOD_CURRENT_WEIGHT,
    BAD_CURRENT_PENALTY_WEIGHT,
    EMERGENCY_TIME_ONLY_ALPHA,
)
from vessel_model import step, bearing_deg, distance_km, current_favorability

logger = logging.getLogger(__name__)

# 6-hour steps per day
STEPS_PER_DAY = 24 // TIMESTEP_HOURS
HORIZON_STEPS = HORIZON_DAYS * STEPS_PER_DAY

# Only log "forecast expired" once per process to avoid spam
_forecast_expired_warned = False


def get_currents_type(lat: float, lon: float, time: datetime) -> Tuple[float, float, bool]:
    """Type hint for current provider: (u_ms, v_ms, forecast_expired)."""
    return (0.0, 0.0, False)


def when_will_current_turn_bad(
    lat: float,
    lon: float,
    current_time: datetime,
    target_lat: float,
    target_lon: float,
    get_currents: Callable[[float, float, datetime], Tuple[float, float, bool]],
    max_steps: int = 20,
    threshold: float = CURRENT_FAVORABILITY_BAD_THRESHOLD,
) -> Tuple[Optional[int], float]:
    """
    Look ahead in time at (lat, lon): when will the current here become unfavorable?
    Returns (steps_until_bad, favorability_now). steps_until_bad = first step index where
    favorability < threshold, or None if it stays good for max_steps. Used to decide
    when we must use propeller to change current before we're stuck in a bad one.
    """
    dt = timedelta(hours=TIMESTEP_HOURS)
    t = current_time
    u, v, _ = get_currents(lat, lon, t)
    fav_now = current_favorability(lat, lon, target_lat, target_lon, u, v)
    for k in range(max_steps):
        u, v, _ = get_currents(lat, lon, t)
        fav = current_favorability(lat, lon, target_lat, target_lon, u, v)
        if fav < threshold:
            return (k, fav_now)
        t = t + dt
    return (None, fav_now)


def _lat_penalty(lat: float, target_lon: float, start_lon: float) -> float:
    """Penalty for being south of limit on eastbound routes."""
    if LATITUDE_PENALTY_WEIGHT <= 0 or lat >= SOUTH_LAT_LIMIT_DEG:
        return 0.0
    # Only penalize when going east (target east of start)
    if target_lon <= start_lon:
        return 0.0
    return LATITUDE_PENALTY_WEIGHT * (SOUTH_LAT_LIMIT_DEG - lat)


def choose_steering(
    lat: float,
    lon: float,
    target_lat: float,
    target_lon: float,
    current_time: datetime,
    get_currents: Callable[[float, float, datetime], Tuple[float, float, bool]],
    forecast_expired: bool = False,
    alpha: float = ALPHA,
    beta: float = BETA,
    horizon_steps: int = HORIZON_STEPS,
    angle_range_deg: float = ANGLE_RANGE_DEG,
    angle_step_deg: float = ANGLE_STEP_DEG,
    motor_available: bool = True,
    wind_available: bool = True,
    sail_efficiency: float = 0.0,
    get_wind: Optional[Callable[[float, float, datetime], Tuple[float, float]]] = None,
    sail_motor_ok: Optional[bool] = None,
    propeller_motor_ok: Optional[bool] = None,
    turning_motors_working: Optional[int] = None,
    emergency_to_shore: bool = False,
) -> Tuple[float, float]:
    """
    Return (steering_angle_deg, cost) for best direction.
    Uses current favorability: good current = toward target; propeller only for changing
    current (or emergency). emergency_to_shore = minimize time to shore, ignore energy.
    """
    sail_ok = sail_motor_ok if sail_motor_ok is not None else wind_available
    prop_ok = propeller_motor_ok if propeller_motor_ok is not None else motor_available
    turn_n = turning_motors_working if turning_motors_working is not None else (2 if motor_available else 0)
    steer_available = prop_ok and turn_n >= 1

    bearing_to_target = bearing_deg(lat, lon, target_lat, target_lon)
    bearing_as_steering = 90.0 - bearing_to_target

    global _forecast_expired_warned
    if forecast_expired:
        angle_range_deg = FORECAST_EXPIRED_ANGLE_RANGE_DEG
        if not _forecast_expired_warned:
            _forecast_expired_warned = True
            logger.warning("Forecast expired: using reduced steering range ±%s deg", angle_range_deg)

    best_angle = bearing_as_steering
    best_cost = 1e30
    alpha_eff = EMERGENCY_TIME_ONLY_ALPHA if emergency_to_shore else alpha

    angles = []
    a = -angle_range_deg
    while a <= angle_range_deg:
        angles.append(bearing_as_steering + a)
        a += angle_step_deg

    for rel_angle in angles:
        cost, _, _ = _simulate_forward(
            lat, lon, current_time, target_lat, target_lon,
            rel_angle, get_currents, horizon_steps, alpha_eff, beta,
            motor_available=steer_available,
            wind_available=sail_ok,
            sail_efficiency=sail_efficiency,
            get_wind=get_wind,
            sail_motor_ok=sail_ok,
            propeller_motor_ok=prop_ok,
            turning_motors_working=turn_n,
            emergency_to_shore=emergency_to_shore,
        )
        if cost < best_cost:
            best_cost = cost
            best_angle = rel_angle

    return (best_angle, best_cost)


def _simulate_forward(
    lat: float,
    lon: float,
    current_time: datetime,
    target_lat: float,
    target_lon: float,
    steering_angle_deg: float,
    get_currents: Callable[[float, float, datetime], Tuple[float, float, bool]],
    n_steps: int,
    alpha: float,
    beta: float,
    motor_available: bool = True,
    wind_available: bool = True,
    sail_efficiency: float = 0.0,
    get_wind: Optional[Callable[[float, float, datetime], Tuple[float, float]]] = None,
    sail_motor_ok: Optional[bool] = None,
    propeller_motor_ok: Optional[bool] = None,
    turning_motors_working: Optional[int] = None,
    emergency_to_shore: bool = False,
) -> Tuple[float, float, float]:
    """
    Simulate n_steps with fixed steering/course. Returns (cost, total_energy, final_dist_km).
    Cost is current-aware: penalize bad currents, save propeller in good currents; emergency = time only.
    """
    sail_ok = sail_motor_ok if sail_motor_ok is not None else wind_available
    prop_ok = propeller_motor_ok if propeller_motor_ok is not None else motor_available
    turn_n = turning_motors_working if turning_motors_working is not None else (2 if motor_available else 0)
    steer_available = prop_ok and turn_n >= 1

    dt = timedelta(hours=TIMESTEP_HOURS)
    total_energy = 0.0
    cost_energy_term = 0.0  # energy term with "save propeller in good current" weighting
    cost_bad_current = 0.0  # penalty for being in bad current (encourage changing lane)
    cur_lat, cur_lon = lat, lon
    cur_time = current_time
    use_sail = sail_ok and sail_efficiency > 0 and get_wind is not None

    for _ in range(n_steps):
        u, v, _ = get_currents(cur_lat, cur_lon, cur_time)
        fav = current_favorability(cur_lat, cur_lon, target_lat, target_lon, u, v)
        u_wind, v_wind = (get_wind(cur_lat, cur_lon, cur_time) if use_sail else (None, None))

        cur_lat, cur_lon, _, _, energy, _, _ = step(
            cur_lat, cur_lon, u, v, steering_angle_deg,
            u_wind_ms=u_wind,
            v_wind_ms=v_wind,
            sail_efficiency=sail_efficiency if use_sail else 0.0,
            motor_available=steer_available,
            sail_motor_ok=sail_ok,
            propeller_motor_ok=prop_ok,
            turning_motors_working=turn_n,
        )
        total_energy += energy
        # Propeller only for changing currents: penalize using prop when in good current
        if steer_available and not emergency_to_shore:
            cost_energy_term += energy * (1.0 + PROPELLER_SAVE_IN_GOOD_CURRENT_WEIGHT * max(0.0, fav))
        else:
            cost_energy_term += energy
        # Penalize being in bad current so we prefer steering into a better one
        if not emergency_to_shore:
            cost_bad_current += BAD_CURRENT_PENALTY_WEIGHT * max(0.0, -fav)
        cur_time = cur_time + dt

        dist = distance_km(cur_lat, cur_lon, target_lat, target_lon)
        lat_pen = _lat_penalty(cur_lat, target_lon, lon)

        if dist <= DISTANCE_TOLERANCE_KM:
            time_days = (cur_time - current_time).total_seconds() / 86400.0
            if emergency_to_shore:
                cost = alpha * time_days + beta * dist + lat_pen
            elif steer_available:
                cost = cost_energy_term + cost_bad_current + alpha * time_days + beta * dist + lat_pen
            else:
                cost = cost_bad_current + alpha * time_days + beta * dist + lat_pen
            return (cost, total_energy, dist)

    dist = distance_km(cur_lat, cur_lon, target_lat, target_lon)
    time_days = (cur_time - current_time).total_seconds() / 86400.0
    lat_pen = _lat_penalty(cur_lat, target_lon, lon)
    if emergency_to_shore:
        cost = alpha * time_days + beta * dist + lat_pen
    elif steer_available:
        cost = cost_energy_term + cost_bad_current + alpha * time_days + beta * dist + lat_pen
    else:
        cost = cost_bad_current + alpha * time_days + beta * dist + lat_pen
    return (cost, total_energy, dist)
