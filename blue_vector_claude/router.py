"""
router.py — Receding-horizon steering optimizer.

Explain like you're 8:
  The router is the brain. At every step it says:
    "If I turn THIS way for the next 5 days, how much gas do I use?"
  It tries many directions in its head and picks the cheapest one.
  The trick: being in a good current is rewarded; being in a bad one is penalised.
"""

import math
from datetime import datetime, timedelta
from typing import Callable, Tuple

from blue_vector_claude.config import (
    TIMESTEP_HOURS, DT_SECONDS,
    ANGLE_RANGE_DEG, ANGLE_STEP_DEG, FORECAST_EXPIRED_ANGLE_RANGE_DEG,
    HORIZON_STEPS,
    ALPHA, BETA,
    BAD_CURRENT_PENALTY_WEIGHT, PROPELLER_SAVE_IN_GOOD_CURRENT_WEIGHT,
    EMERGENCY_TIME_ONLY_ALPHA, DISTANCE_TOLERANCE_KM,
)
from blue_vector_claude.vessel_model import (
    step, bearing_deg, bearing_to_math_angle,
    distance_km, current_favorability,
)


# ── Internal forward simulation ───────────────────────────────────────────────

def _simulate_forward(
    lat: float,
    lon: float,
    current_time: datetime,
    target_lat: float,
    target_lon: float,
    steering_angle_deg: float,    # math angle (0=East, 90=North)
    get_currents: Callable,       # (lat, lon, time) → (u, v, expired)
    get_wind: Callable,           # (lat, lon, time) → (u_wind, v_wind)
    n_steps: int = HORIZON_STEPS,
    sail_motor_ok: bool = True,
    propeller_motor_ok: bool = True,
    turning_motors_working: int = 2,
    emergency: bool = False,
    alpha: float = ALPHA,
    beta: float = BETA,
) -> Tuple[float, float, float]:
    """
    Simulate n_steps into the future using a fixed steering angle.
    Returns (total_cost, final_lat, final_lon).

    Cost per step:
        - Energy term (penalise motor use in good currents — save it for lane changes)
        - Bad-current penalty (push the boat into better lanes)
        - Time (α × days elapsed)
    Final cost adds:
        - Distance to target (β × km remaining)
    """
    cost = 0.0
    cur_lat, cur_lon = lat, lon
    cur_time = current_time

    dt_hours = TIMESTEP_HOURS
    elapsed_days = 0.0

    for _ in range(n_steps):
        u, v, _ = get_currents(cur_lat, cur_lon, cur_time)
        u_w, v_w = get_wind(cur_lat, cur_lon, cur_time)

        new_lat, new_lon, dx_s, dy_s, energy, dx_sail, dy_sail = step(
            cur_lat, cur_lon,
            u, v,
            steering_angle_deg,
            u_w, v_w,
            sail_motor_ok=sail_motor_ok,
            propeller_motor_ok=propeller_motor_ok,
            turning_motors_working=turning_motors_working,
        )

        fav = current_favorability(cur_lat, cur_lon, target_lat, target_lon, u, v)

        if not emergency:
            # Penalise running motor hard when current is already helping
            energy_term = energy * (
                1.0 + PROPELLER_SAVE_IN_GOOD_CURRENT_WEIGHT * max(0.0, fav)
            )
            # Penalise being in a bad-current lane
            bad_current_term = BAD_CURRENT_PENALTY_WEIGHT * max(0.0, -fav)
            cost += energy_term + bad_current_term
        # In emergency mode we ignore energy — just minimise time

        elapsed_days += dt_hours / 24.0
        cost += alpha * (dt_hours / 24.0)  # time cost per step

        cur_lat, cur_lon = new_lat, new_lon
        cur_time = cur_time + timedelta(hours=dt_hours)

        # Early exit if we've arrived
        if distance_km(cur_lat, cur_lon, target_lat, target_lon) <= DISTANCE_TOLERANCE_KM:
            break

    # Final distance cost
    dist_remaining = distance_km(cur_lat, cur_lon, target_lat, target_lon)
    cost += beta * dist_remaining

    return cost, cur_lat, cur_lon


# ── Public optimizer ──────────────────────────────────────────────────────────

def choose_steering(
    lat: float,
    lon: float,
    target_lat: float,
    target_lon: float,
    current_time: datetime,
    get_currents: Callable,
    get_wind: Callable,
    forecast_expired: bool = False,
    sail_motor_ok: bool = True,
    propeller_motor_ok: bool = True,
    turning_motors_working: int = 2,
    emergency: bool = False,
    alpha: float = ALPHA,
    beta: float = BETA,
) -> Tuple[float, float]:
    """
    Pick the best steering angle for the current timestep.

    Strategy: receding-horizon search over candidate angles.
    Candidates are evenly spaced around the bearing to the target,
    within ±ANGLE_RANGE_DEG (reduced to ±FORECAST_EXPIRED_ANGLE_RANGE_DEG when stale).

    Returns:
        (best_angle_deg, best_cost)
        best_angle_deg is a math angle (0=East, 90=North), ready for vessel_model.step().
    """
    # Compass bearing → math angle reference
    compass = bearing_deg(lat, lon, target_lat, target_lon)
    angle_ref = bearing_to_math_angle(compass)

    angle_range = (
        FORECAST_EXPIRED_ANGLE_RANGE_DEG if forecast_expired else ANGLE_RANGE_DEG
    )

    # Build candidate list
    n_candidates = int(2 * angle_range / ANGLE_STEP_DEG) + 1
    candidates = [
        angle_ref - angle_range + i * ANGLE_STEP_DEG
        for i in range(n_candidates)
    ]

    best_angle = angle_ref  # default: straight toward target
    best_cost = math.inf

    for angle in candidates:
        cost, _, _ = _simulate_forward(
            lat, lon, current_time,
            target_lat, target_lon,
            angle,
            get_currents, get_wind,
            sail_motor_ok=sail_motor_ok,
            propeller_motor_ok=propeller_motor_ok,
            turning_motors_working=turning_motors_working,
            emergency=emergency,
            alpha=alpha,
            beta=beta,
        )
        if cost < best_cost:
            best_cost = cost
            best_angle = angle

    return best_angle, best_cost
