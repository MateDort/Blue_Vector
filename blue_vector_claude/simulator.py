"""
simulator.py — Full route simulation from start to target.

Explain like you're 8:
  This is the full game. Start at A, and every 6 hours ask the router
  "which way?", move the boat, and repeat until we reach B or run out
  of time. At the end it tells you how long it took and how much energy
  you saved compared to going in a straight line with the motor.
"""

import math
from datetime import datetime, timedelta
from typing import Optional, Tuple, List

from blue_vector_claude.config import (
    TIMESTEP_HOURS, DISTANCE_TOLERANCE_KM, ALPHA, BETA,
    MAX_STEERING_SPEED_MS,
)
from blue_vector_claude.vessel_model import (
    step, distance_km, straight_line_energy,
)
from blue_vector_claude.router import choose_steering
from blue_vector_claude.wind_model import get_wind as _parametric_wind


def _noop_wind(lat, lon, time):
    return 0.0, 0.0


def simulate_route(
    start_lat: float,
    start_lon: float,
    target_lat: float,
    target_lon: float,
    max_days: float,
    current_provider,
    wind_provider=None,           # object with get_wind(lat, lon, time), or None
    start_time: Optional[datetime] = None,
    sail_motor_ok: bool = True,
    propeller_motor_ok: bool = True,
    turning_motors_working: int = 2,
    alpha: float = ALPHA,
    beta: float = BETA,
) -> tuple:
    """
    Run the full route from (start_lat, start_lon) to (target_lat, target_lon).

    Args:
        current_provider: object with get_currents(lat, lon, time) → (u, v, expired)
        wind_provider: object with get_wind(lat, lon, time) → (u, v), or None for no wind
        max_days: stop if we haven't arrived by this many days

    Returns:
        (trajectory, times, total_days, total_energy, percent_saved, mode, sail_fraction)

        trajectory   : list of (lat, lon) tuples
        times        : list of datetime at each waypoint
        total_days   : float — trip duration in days
        total_energy : float — total propulsion energy consumed
        percent_saved: float — energy saved vs straight-line baseline (can be negative)
        mode         : str — "combined" | "motor_only" | "sail_only" | "drift_only"
        sail_fraction: float in [0, 1] — fraction of displacement from sail
    """
    if start_time is None:
        start_time = datetime.utcnow()

    # Determine vessel mode
    if propeller_motor_ok and sail_motor_ok:
        mode = "combined"
    elif propeller_motor_ok:
        mode = "motor_only"
    elif sail_motor_ok:
        mode = "sail_only"
    else:
        mode = "drift_only"

    # Wind function
    if wind_provider is not None:
        get_wind = wind_provider.get_wind
    elif sail_motor_ok:
        get_wind = _parametric_wind   # use built-in parametric model
    else:
        get_wind = _noop_wind

    # Initialise state
    lat, lon = start_lat, start_lon
    current_time = start_time
    elapsed_days = 0.0

    trajectory: List[Tuple[float, float]] = [(lat, lon)]
    times: List[datetime] = [current_time]

    total_energy = 0.0
    total_sail_disp = 0.0   # metres
    total_disp = 0.0        # metres (all sources)

    forecast_expired = False
    prev_dist = distance_km(start_lat, start_lon, target_lat, target_lon)
    arrived = False

    # ── Main loop ────────────────────────────────────────────────────────────
    while True:
        dist = distance_km(lat, lon, target_lat, target_lon)

        # Primary arrival check
        if dist <= DISTANCE_TOLERANCE_KM:
            arrived = True
            break

        # Overshoot detection: if we were close (< 150 km) and are now moving away
        if prev_dist < 150.0 and dist > prev_dist:
            arrived = True
            break

        if elapsed_days >= max_days:
            break

        prev_dist = dist

        # Get currents at current position + time
        u, v, forecast_expired = current_provider.get_currents(lat, lon, current_time)

        # Get wind
        u_w, v_w = get_wind(lat, lon, current_time)

        # Choose best steering angle
        angle, _ = choose_steering(
            lat, lon,
            target_lat, target_lon,
            current_time,
            current_provider.get_currents,
            get_wind,
            forecast_expired=forecast_expired,
            sail_motor_ok=sail_motor_ok,
            propeller_motor_ok=propeller_motor_ok,
            turning_motors_working=turning_motors_working,
            alpha=alpha,
            beta=beta,
        )

        # Move the vessel one step
        new_lat, new_lon, dx_s, dy_s, energy, dx_sail, dy_sail = step(
            lat, lon, u, v, angle, u_w, v_w,
            sail_motor_ok=sail_motor_ok,
            propeller_motor_ok=propeller_motor_ok,
            turning_motors_working=turning_motors_working,
        )

        # Accumulate
        total_energy += energy
        from blue_vector_claude.config import DT_SECONDS as _DT
        # Total displacement = current + sail + motor contributions (all in metres)
        dx_current = u * _DT
        dy_current = v * _DT
        dx_tot = dx_current + dx_sail + dx_s
        dy_tot = dy_current + dy_sail + dy_s
        step_disp = math.sqrt(dx_tot ** 2 + dy_tot ** 2)
        sail_disp = math.sqrt(dx_sail ** 2 + dy_sail ** 2)
        total_sail_disp += sail_disp
        total_disp += max(step_disp, 1e-9)

        # Update position and time
        lat, lon = new_lat, new_lon
        current_time += timedelta(hours=TIMESTEP_HOURS)
        elapsed_days += TIMESTEP_HOURS / 24.0

        trajectory.append((lat, lon))
        times.append(current_time)

    # ── Snap last position exactly to target when arrived ────────────────────
    # The last trajectory point is within DISTANCE_TOLERANCE_KM of target.
    # Replace it with the exact target so the route ends precisely there.
    if arrived and trajectory:
        last_lon = trajectory[-1][1]
        # Convert target_lon to the same "extended" convention as the trajectory
        # (trajectory lon may have passed through ±180 and kept increasing/decreasing)
        ext_target_lon = target_lon
        while ext_target_lon - last_lon > 180:
            ext_target_lon -= 360
        while last_lon - ext_target_lon > 180:
            ext_target_lon += 360
        trajectory[-1] = (target_lat, ext_target_lon)

    # ── Post-loop statistics ─────────────────────────────────────────────────
    total_days = elapsed_days

    straight_dist_km = distance_km(start_lat, start_lon, target_lat, target_lon)
    _, baseline_energy = straight_line_energy(straight_dist_km, MAX_STEERING_SPEED_MS)

    if mode == "sail_only" or mode == "drift_only":
        percent_saved = 100.0  # no motor used
    elif baseline_energy > 0:
        percent_saved = (1.0 - total_energy / baseline_energy) * 100.0
    else:
        percent_saved = 0.0

    # Clip to [0, 1] — can exceed 1 when opposing currents reduce total displacement
    # below the sail contribution alone (mathematically valid but confusing to report)
    sail_fraction = min(1.0, total_sail_disp / max(total_disp, 1e-9))

    return (
        trajectory,
        times,
        total_days,
        total_energy,
        percent_saved,
        mode,
        sail_fraction,
    )
