"""
data_loader.py — Fetch NOAA RTOFS ocean current data via OPeNDAP and cache locally.

Explain like you're 8:
  This file is the "weather report for the ocean". It either gets real data
  from the NOAA website or makes up a simple grid so we can still run the
  simulation offline. When you ask "how fast is the water moving here, now?"
  this file answers.

Data source: NOAA RTOFS (Real-Time Ocean Forecast System) — public, no token needed.
URL: https://nomads.ncep.noaa.gov/dods/rtofs/rtofs_global{YYYYMMDD}/rtofs_glo_2ds_nowcast_hrly_prog
Variables: u_velocity, v_velocity (m/s), lat, lon, time
"""

import os
import time as _time
import math
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
import xarray as xr

from blue_vector_claude.config import (
    DEFAULT_BBOX, NETCDF_CACHE_PATH, CACHE_MAX_AGE_HOURS,
)

logger = logging.getLogger(__name__)

_RTOFS_URL_TEMPLATE = (
    "https://nomads.ncep.noaa.gov/dods/rtofs/"
    "rtofs_global{date}/rtofs_glo_2ds_nowcast_hrly_prog"
)


# ── Download / build dataset ──────────────────────────────────────────────────

def _rtofs_url(date: datetime) -> str:
    return _RTOFS_URL_TEMPLATE.format(date=date.strftime("%Y%m%d"))


def _try_fetch_rtofs(
    bbox: Tuple[float, float, float, float],
    start_time: datetime,
    forecast_days: int,
) -> Optional[xr.Dataset]:
    """
    Attempt to open RTOFS for today or yesterday, subset by bbox and time window.
    Returns xarray Dataset or None on failure.
    """
    lat_min, lon_min, lat_max, lon_max = bbox
    end_time = start_time + timedelta(days=forecast_days)

    for days_back in range(3):
        run_date = datetime.utcnow() - timedelta(days=days_back)
        url = _rtofs_url(run_date)
        try:
            logger.info("Trying RTOFS: %s", url)
            ds = xr.open_dataset(url, engine="pydap", decode_times=True)

            # RTOFS variable names vary; handle both naming conventions
            u_name = "u_velocity" if "u_velocity" in ds else "utrans"
            v_name = "v_velocity" if "v_velocity" in ds else "vtrans"

            # Normalise coordinate names
            lat_name = "lat" if "lat" in ds.coords else "Latitude"
            lon_name = "lon" if "lon" in ds.coords else "Longitude"

            lats = ds[lat_name].values
            lons = ds[lon_name].values

            # Spatial slice
            lat_idx = np.where((lats >= lat_min) & (lats <= lat_max))[0]
            lon_idx = np.where((lons >= lon_min) & (lons <= lon_max))[0]

            if len(lat_idx) == 0 or len(lon_idx) == 0:
                logger.warning("No grid points in bbox for run %s", run_date.date())
                continue

            ds_sub = ds.isel(
                **{lat_name: lat_idx, lon_name: lon_idx}
            )[[u_name, v_name]]

            # Rename to standard names for CurrentProvider
            rename = {}
            if u_name != "u_velocity":
                rename[u_name] = "u_velocity"
            if v_name != "v_velocity":
                rename[v_name] = "v_velocity"
            if lat_name != "lat":
                rename[lat_name] = "lat"
            if lon_name != "lon":
                rename[lon_name] = "lon"
            if rename:
                ds_sub = ds_sub.rename(rename)

            logger.info("RTOFS fetch successful for run %s", run_date.date())
            return ds_sub

        except Exception as exc:
            logger.warning("RTOFS fetch failed for run %s: %s", run_date.date(), exc)

    return None


def _build_synthetic(
    bbox: Tuple[float, float, float, float],
    start_time: datetime,
    forecast_days: int,
) -> xr.Dataset:
    """
    Build a tiny synthetic dataset with a weak westward current.
    Used when RTOFS is unavailable (no internet, server down, etc.).
    """
    lat_min, lon_min, lat_max, lon_max = bbox
    lats = np.linspace(lat_min, lat_max, 20)
    lons = np.linspace(lon_min, lon_max, 20)

    times = [start_time + timedelta(hours=6 * i) for i in range(forecast_days * 4 + 1)]

    # Weak westward flow (~0.05 m/s), small northward component
    u = np.full((len(times), len(lats), len(lons)), -0.05, dtype=np.float32)
    v = np.full((len(times), len(lats), len(lons)), 0.01, dtype=np.float32)

    ds = xr.Dataset(
        {
            "u_velocity": (["time", "lat", "lon"], u),
            "v_velocity": (["time", "lat", "lon"], v),
        },
        coords={
            "time": times,
            "lat": lats,
            "lon": lons,
        },
    )
    logger.info("Built synthetic current dataset (%d time steps)", len(times))
    return ds


def fetch_and_save(
    bbox: Tuple[float, float, float, float] = DEFAULT_BBOX,
    start_time: Optional[datetime] = None,
    forecast_days: int = 7,
    cache_path: str = NETCDF_CACHE_PATH,
) -> xr.Dataset:
    """
    Fetch RTOFS data (or build synthetic fallback) and save to local NetCDF.
    Returns the xarray Dataset.
    """
    if start_time is None:
        start_time = datetime.utcnow()

    Path(cache_path).parent.mkdir(parents=True, exist_ok=True)

    ds = _try_fetch_rtofs(bbox, start_time, forecast_days)
    if ds is None:
        logger.warning("All RTOFS attempts failed — using synthetic data")
        ds = _build_synthetic(bbox, start_time, forecast_days)

    ds.to_netcdf(cache_path)
    logger.info("Saved dataset to %s", cache_path)
    return ds


# ── CurrentProvider ───────────────────────────────────────────────────────────

class CurrentProvider:
    """
    Wraps an xarray Dataset and provides current interpolation at arbitrary (lat, lon, time).

    Usage:
        provider = CurrentProvider(ds)
        u, v, expired = provider.get_currents(35.0, -70.0, datetime.utcnow())
    """

    def __init__(self, ds: xr.Dataset):
        self.ds = ds
        self._times = ds["time"].values  # numpy datetime64 array

    def get_currents(self, lat: float, lon: float, time: datetime) -> Tuple[float, float, bool]:
        """
        Interpolate ocean currents at (lat, lon, time).

        Returns:
            (u_ms, v_ms, forecast_expired)
            u_ms > 0 = eastward, v_ms > 0 = northward.
            forecast_expired = True if time is beyond the last data point.
        """
        # Check if the requested time is within the dataset
        t_np = np.datetime64(time.replace(tzinfo=None))
        last_t = self._times[-1]

        if t_np > last_t:
            forecast_expired = True
            # Use the last available time slice
            ds_slice = self.ds.isel(time=-1)
            pt = ds_slice.interp(lat=lat, lon=lon, method="linear")
        else:
            forecast_expired = False
            t_da = xr.DataArray(t_np)
            pt = self.ds.interp(lat=lat, lon=lon, time=t_da, method="linear")

        u = float(pt["u_velocity"].values)
        v = float(pt["v_velocity"].values)

        # Replace NaN (land mask, out-of-range) with zero
        if math.isnan(u):
            u = 0.0
        if math.isnan(v):
            v = 0.0

        return u, v, forecast_expired

    def get_dataset(self) -> xr.Dataset:
        """Return the underlying xarray Dataset (used by viz for quiver plots)."""
        return self.ds


# ── open_cached ───────────────────────────────────────────────────────────────

def open_cached(
    bbox: Tuple[float, float, float, float] = DEFAULT_BBOX,
    start_time: Optional[datetime] = None,
    forecast_days: int = 7,
    cache_path: str = NETCDF_CACHE_PATH,
) -> CurrentProvider:
    """
    Load from local NetCDF cache if fresh, otherwise download and save.

    A cache is "fresh" if it was written within CACHE_MAX_AGE_HOURS.

    Returns:
        CurrentProvider ready to call get_currents(lat, lon, time).
    """
    if start_time is None:
        start_time = datetime.utcnow()

    cache_file = Path(cache_path)
    cache_fresh = (
        cache_file.exists()
        and (_time.time() - cache_file.stat().st_mtime) < CACHE_MAX_AGE_HOURS * 3600
    )

    if cache_fresh:
        logger.info("Loading currents from cache: %s", cache_path)
        ds = xr.open_dataset(cache_path)
    else:
        logger.info("Cache missing or stale — fetching from RTOFS")
        ds = fetch_and_save(bbox, start_time, forecast_days, cache_path)

    return CurrentProvider(ds)
