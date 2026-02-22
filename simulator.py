"""
Simulator: simulate_route(start, target, max_days) using current provider, vessel_model, router.
Returns trajectory, times, energy, percent_saved, mode, sail stats.
Supports motor_only, sail_only, combined; optional get_wind for sail.
"""
import logging
from datetime import datetime, timedelta
from typing import List, Tuple, Optional, Any

from config import (
    TIMESTEP_HOURS,
    DISTANCE_TOLERANCE_KM,
    SAIL_EFFICIENCY,
    SAIL_MOTOR_AVAILABLE,
    PROPELLER_MOTOR_AVAILABLE,
    TURNING_MOTORS_WORKING,
)
from vessel_model import step, distance_km, straight_line_energy_km
from router import choose_steering
from wind_model import get_wind as _get_wind_param

logger = logging.getLogger(__name__)

STEPS_PER_DAY = 24 // TIMESTEP_HOURS


def simulate_route(
    start_lat: float,
    start_lon: float,
    target_lat: float,
    target_lon: float,
    max_days: float,
    current_provider: Any,  # CurrentProvider or MockCurrentProvider
    start_time: Optional[datetime] = None,
    motor_available: Optional[bool] = None,
    wind_available: Optional[bool] = None,
    sail_efficiency: Optional[float] = None,
    get_wind: Optional[Any] = None,
    sail_motor_ok: Optional[bool] = None,
    propeller_motor_ok: Optional[bool] = None,
    turning_motors_working: Optional[int] = None,
    emergency_to_shore: bool = False,
) -> Tuple[
    List[Tuple[float, float]],
    List[datetime],
    float,
    float,
    float,
    str,
    float,
]:
    """
    Run receding-horizon routing from start to target.
    Returns:
        trajectory: list of (lat, lon)
        times: list of datetime at each point
        total_time_days
        total_propulsion_energy
        percent_energy_saved (vs straight-line; N/A in sail-only use 100 or 0)
        mode: "combined" | "motor_only" | "sail_only"
        sail_fraction: fraction of total displacement from sail (0-1)
    """
    if start_time is None:
        start_time = datetime.utcnow()
    # 4 motors: sail, propeller, 2× turning
    sail_ok = SAIL_MOTOR_AVAILABLE if sail_motor_ok is None else sail_motor_ok
    prop_ok = PROPELLER_MOTOR_AVAILABLE if propeller_motor_ok is None else propeller_motor_ok
    turn_n = TURNING_MOTORS_WORKING if turning_motors_working is None else turning_motors_working
    # Steering = propeller ok and at least 1 turning motor; sail = sail motor ok
    motor_ok = prop_ok and turn_n >= 1
    wind_ok = sail_ok
    sail_eff = SAIL_EFFICIENCY if sail_efficiency is None else sail_efficiency
    get_wind_fn = get_wind if get_wind is not None else (_get_wind_param if wind_ok else None)

    if emergency_to_shore:
        mode = "emergency_to_shore"
    elif motor_ok and wind_ok:
        mode = "combined"
    elif motor_ok:
        mode = "propeller_only"
    elif wind_ok:
        mode = "sail_only"
    else:
        mode = "drift_only"

    trajectory: List[Tuple[float, float]] = [(start_lat, start_lon)]
    times: List[datetime] = [start_time]
    total_energy = 0.0
    total_displacement_m = 0.0
    sail_displacement_m = 0.0
    dt = timedelta(hours=TIMESTEP_HOURS)
    max_steps = int(max_days * STEPS_PER_DAY)
    forecast_expired = False
    use_sail = wind_ok and sail_eff > 0 and get_wind_fn is not None

    def get_currents(lat: float, lon: float, t: datetime) -> Tuple[float, float, bool]:
        u, v, expired = current_provider.get_currents(lat, lon, t)
        nonlocal forecast_expired
        if expired:
            forecast_expired = True
        return (u, v, expired)

    for _ in range(max_steps):
        lat, lon = trajectory[-1]
        cur_time = times[-1]
        dist_km = distance_km(lat, lon, target_lat, target_lon)
        if dist_km <= DISTANCE_TOLERANCE_KM:
            break

        steering_angle, _ = choose_steering(
            lat, lon, target_lat, target_lon, cur_time, get_currents, forecast_expired,
            motor_available=motor_ok,
            wind_available=wind_ok,
            sail_efficiency=sail_eff,
            get_wind=get_wind_fn,
            sail_motor_ok=sail_ok,
            propeller_motor_ok=prop_ok,
            turning_motors_working=turn_n,
            emergency_to_shore=emergency_to_shore,
        )
        u, v, _ = get_currents(lat, lon, cur_time)
        u_w, v_w = (get_wind_fn(lat, lon, cur_time) if use_sail else (None, None))

        new_lat, new_lon, dx_steer, dy_steer, energy_step, dx_sail, dy_sail = step(
            lat, lon, u, v, steering_angle,
            u_wind_ms=u_w,
            v_wind_ms=v_w,
            sail_efficiency=sail_eff if use_sail else 0.0,
            motor_available=motor_ok,
            sail_motor_ok=sail_ok,
            propeller_motor_ok=prop_ok,
            turning_motors_working=turn_n,
        )
        total_energy += energy_step
        step_disp = (abs(new_lat - lat) * 111320e3 / 360) ** 2 + (abs(new_lon - lon) * 111320e3 * 0.7 / 360) ** 2
        step_disp = step_disp ** 0.5  # rough meters
        total_displacement_m += step_disp
        sail_displacement_m += (dx_sail**2 + dy_sail**2) ** 0.5
        trajectory.append((new_lat, new_lon))
        times.append(cur_time + dt)

    total_time_days = (times[-1] - times[0]).total_seconds() / 86400.0
    sail_fraction = (sail_displacement_m / total_displacement_m) if total_displacement_m > 0 else 0.0

    straight_dist_km = distance_km(start_lat, start_lon, target_lat, target_lon)
    _, baseline_energy = straight_line_energy_km(straight_dist_km)
    if baseline_energy > 0 and motor_ok:
        percent_energy_saved = (1.0 - total_energy / baseline_energy) * 100.0
    elif not motor_ok:
        percent_energy_saved = 100.0  # no propulsion used
    else:
        percent_energy_saved = 0.0

    return (
        trajectory,
        times,
        total_time_days,
        total_energy,
        percent_energy_saved,
        mode,
        sail_fraction,
    )
