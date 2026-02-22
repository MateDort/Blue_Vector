#!/usr/bin/env python3
"""
FastAPI server for Blue Vector: run the real routing algorithm with mocked or real data.
POST /simulate returns trajectory and stats for the web app to animate.
Real ocean current data is downloaded on first run (Pacific China→LA) and used for 60-day simulation.
"""
import logging
from datetime import datetime
from typing import List, Optional, Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config import (
    PACIFIC_BBOX_CHINA_LA,
    CHINA_LA_START,
    CHINA_LA_TARGET,
    DEFAULT_PACIFIC_FORECAST_DAYS,
    DEFAULT_PACIFIC_MAX_DAYS,
)
from data_loader import open_cached
from mock_data import (
    MockCurrentProvider,
    preset_favorable_eastbound,
    preset_unfavorable_westbound,
    preset_cross_current,
    preset_calm,
)
from simulator import simulate_route

logger = logging.getLogger(__name__)

app = FastAPI(title="Blue Vector API", description="Ocean-current routing with wind/sail")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PRESETS = {
    "favorable": preset_favorable_eastbound,
    "unfavorable": preset_unfavorable_westbound,
    "cross": preset_cross_current,
    "calm": preset_calm,
}


class SimulateRequest(BaseModel):
    start_lat: float = 32.0
    start_lon: float = -120.0
    target_lat: float = 35.0
    target_lon: float = -115.0
    max_days: float = 14.0
    mode: Literal["combined", "motor_only", "sail_only"] = "combined"
    scenario: Literal["favorable", "unfavorable", "cross", "calm"] = "favorable"
    # Optional custom constant current (m/s) instead of scenario
    custom_u: Optional[float] = None
    custom_v: Optional[float] = None
    # Real data: use satellite/NOAA currents for Pacific China→LA (download on first run)
    use_real_data: bool = False
    # Motor failed (legacy): same as propeller_motor_failed=True for recalc from current position
    motor_failed: bool = False
    from_lat: Optional[float] = None
    from_lon: Optional[float] = None
    start_time_iso: Optional[str] = None  # ISO datetime when motor failed (for continuing sim)
    # 4 motors: 1 sail, 1 propeller, 2 turning. Set failed=True or turning_failed=0/1/2 to override.
    sail_motor_failed: Optional[bool] = None
    propeller_motor_failed: Optional[bool] = None
    turning_motors_failed: Optional[int] = None  # 0, 1, or 2 (how many of the 2 turning motors failed)
    # Emergency to shore: minimize time only (storm etc.), ignore energy
    emergency_to_shore: bool = False


class SimulateResponse(BaseModel):
    trajectory: List[dict]  # [{"lat": float, "lon": float}, ...]
    times: List[str]  # ISO datetime strings
    total_time_days: float
    total_energy: float
    percent_energy_saved: float
    mode: str
    sail_fraction: float


def _get_current_provider(req: SimulateRequest):
    """Resolve current data: real Pacific data or mock presets."""
    if req.use_real_data:
        try:
            provider = open_cached(
                bbox=PACIFIC_BBOX_CHINA_LA,
                start_time=datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0),
                forecast_days=DEFAULT_PACIFIC_FORECAST_DAYS,
            )
            logger.info("Using real ocean current data for Pacific China→LA")
            return provider
        except Exception as e:
            logger.warning("Real data unavailable (%s), falling back to favorable mock", e)
            return preset_favorable_eastbound()
    if req.custom_u is not None and req.custom_v is not None:
        return MockCurrentProvider(u_ms=req.custom_u, v_ms=req.custom_v)
    return PRESETS.get(req.scenario, preset_favorable_eastbound)()


@app.post("/simulate", response_model=SimulateResponse)
def simulate(req: SimulateRequest) -> SimulateResponse:
    """Run the routing algorithm; returns trajectory for animation. Uses real current data when use_real_data=True."""
    provider = _get_current_provider(req)

    # Motor failed (legacy): recalculate from current position with propeller off → sail only
    if req.motor_failed and req.from_lat is not None and req.from_lon is not None and req.start_time_iso:
        try:
            start_time = datetime.fromisoformat(req.start_time_iso.replace("Z", "+00:00"))
        except Exception:
            start_time = datetime.utcnow()
        start_lat, start_lon = req.from_lat, req.from_lon
        max_days = req.max_days
        sail_motor_ok = not (req.sail_motor_failed if req.sail_motor_failed is not None else False)
        propeller_motor_ok = False  # legacy motor_failed = propeller failed
        turning_motors_working = 2 - min(2, max(0, req.turning_motors_failed or 0))
    else:
        start_time = datetime.utcnow()
        start_lat, start_lon = req.start_lat, req.start_lon
        max_days = req.max_days
        # 4 motors: derive from explicit flags or legacy mode
        if req.sail_motor_failed is not None or req.propeller_motor_failed is not None or req.turning_motors_failed is not None:
            sail_motor_ok = not (req.sail_motor_failed or False)
            propeller_motor_ok = not (req.propeller_motor_failed or False)
            turning_motors_working = 2 - min(2, max(0, req.turning_motors_failed or 0))
        else:
            motor_ok = req.mode != "sail_only"
            wind_ok = req.mode != "motor_only"
            sail_motor_ok = wind_ok
            propeller_motor_ok = motor_ok
            turning_motors_working = 2 if motor_ok else 0

    # China→LA with real data: use 60 days by default
    if req.use_real_data and not (req.motor_failed and req.from_lat is not None):
        max_days = max(max_days, DEFAULT_PACIFIC_MAX_DAYS)

    try:
        trajectory, times, total_time_days, total_energy, percent_saved, mode, sail_fraction = simulate_route(
            start_lat,
            start_lon,
            req.target_lat,
            req.target_lon,
            max_days,
            provider,
            start_time=start_time,
            sail_motor_ok=sail_motor_ok,
            propeller_motor_ok=propeller_motor_ok,
            turning_motors_working=turning_motors_working,
            emergency_to_shore=req.emergency_to_shore,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return SimulateResponse(
        trajectory=[{"lat": p[0], "lon": p[1]} for p in trajectory],
        times=[t.isoformat() for t in times],
        total_time_days=total_time_days,
        total_energy=total_energy,
        percent_energy_saved=percent_saved,
        mode=mode,
        sail_fraction=sail_fraction,
    )


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/ensure_data")
def ensure_data() -> dict:
    """Download real ocean current data for Pacific China→LA. Call before first 60-day simulation."""
    try:
        open_cached(
            bbox=PACIFIC_BBOX_CHINA_LA,
            start_time=datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0),
            forecast_days=DEFAULT_PACIFIC_FORECAST_DAYS,
        )
        return {"status": "ok", "data_ready": True}
    except Exception as e:
        logger.warning("ensure_data failed: %s", e)
        return {"status": "error", "detail": str(e), "data_ready": False}
