"""
Data layer: fetch and cache ocean surface current data (u, v); expose get_currents(lat, lon, time).
Supports NOAA RTOFS (OPeNDAP) and local NetCDF. Offline mode: read only from disk.
"""
import os
import logging
from datetime import datetime
from typing import Tuple, Optional

import numpy as np
import xarray as xr

from config import DATA_DIR, DEFAULT_BBOX, DEFAULT_START_TIME, DEFAULT_FORECAST_DAYS

logger = logging.getLogger(__name__)

# Common variable names in RTOFS / Copernicus-style NetCDF
U_NAMES = ("u", "u_velocity", "uo", "vozocrtx")
V_NAMES = ("v", "v_velocity", "vo", "vomecrty")
LAT_NAMES = ("lat", "latitude", "Latitude", "nav_lat")
LON_NAMES = ("lon", "longitude", "Longitude", "nav_lon")
TIME_NAMES = ("time", "Time", "time_counter", "ocean_time")


def _find_var(ds: xr.Dataset, candidates: tuple) -> Optional[str]:
    for name in candidates:
        if name in ds.variables:
            return name
    return None


def _normalize_dims(ds: xr.Dataset, u_var: str) -> xr.Dataset:
    """Ensure we have lat, lon, time dimension names for consistent indexing."""
    ds = ds.copy(deep=False)
    # Map common dim names to lat, lon, time
    dim_map = {}
    for v in ds.variables:
        if v in ("lat", "latitude", "y", "Y"):
            dim_map[v] = "lat"
        if v in ("lon", "longitude", "x", "X"):
            dim_map[v] = "lon"
        if v in ("time", "Time", "time_counter", "ocean_time"):
            dim_map[v] = "time"
    # Rename dims only if we have 1:1 mapping
    to_rename = {k: v for k, v in dim_map.items() if k in ds.dims and k != v}
    if to_rename:
        ds = ds.rename_dims(to_rename)
    return ds


def ensure_data_dir(data_dir: Optional[str] = None) -> str:
    d = data_dir if data_dir is not None else DATA_DIR
    os.makedirs(d, exist_ok=True)
    return d


def build_rtofs_opendap_url(date: datetime) -> str:
    """
    Build NOAA RTOFS global OPeNDAP URL for a given date.
    NCEI THREDDS catalog structure; fallback base for Atlantic.
    """
    # NCEI THREDDS RTOFS global (example pattern - may need adjustment per actual catalog)
    date_str = date.strftime("%Y%m%d")
    base = "https://www.ncei.noaa.gov/thredds-ocean/dodsC/ncdcOceans/rtofs"
    return f"{base}/rtofs_{date_str}/rtofs_glo_3dz_f{date_str}_daily_3zuio.nc"


def fetch_and_save(
    bbox: Tuple[float, float, float, float],
    start_time: datetime,
    forecast_days: int,
    local_path: Optional[str] = None,
    opendap_url: Optional[str] = None,
    data_dir: Optional[str] = None,
) -> str:
    """
    Fetch ocean current data and save as NetCDF under data_dir or DATA_DIR.
    bbox: (lat_min, lon_min, lat_max, lon_max)
    Returns path to saved file. Uses opendap_url if provided, else builds RTOFS URL.
    """
    d = data_dir if data_dir is not None else DATA_DIR
    ensure_data_dir(d)
    if local_path is None:
        fname = f"currents_{start_time.strftime('%Y%m%d')}_{forecast_days}d.nc"
        local_path = os.path.join(d, fname)

    if opendap_url is None:
        opendap_url = build_rtofs_opendap_url(start_time)

    try:
        logger.info("Opening OPeNDAP: %s", opendap_url)
        ds = xr.open_dataset(opendap_url)
        # Subset by bbox and time if possible
        lat_min, lon_min, lat_max, lon_max = bbox
        # Subset by lat/lon (variable names depend on dataset)
        lat_var = _find_var(ds, LAT_NAMES)
        lon_var = _find_var(ds, LON_NAMES)
        if lat_var and lon_var:
            ds = ds.where(
                (ds[lat_var] >= lat_min)
                & (ds[lat_var] <= lat_max)
                & (ds[lon_var] >= lon_min)
                & (ds[lon_var] <= lon_max),
                drop=True,
            )
        ds.to_netcdf(local_path)
        ds.close()
        logger.info("Saved to %s", local_path)
        return local_path
    except Exception as e:
        logger.warning("OPeNDAP fetch failed (%s). Creating synthetic dataset for offline demo.", e)
        # Synthetic dataset so the rest of the pipeline runs without network
        ds = _create_synthetic_dataset(bbox, start_time, forecast_days)
        ds.to_netcdf(local_path)
        ds.close()
        return local_path


def _create_synthetic_dataset(
    bbox: Tuple[float, float, float, float],
    start_time: datetime,
    forecast_days: int,
) -> xr.Dataset:
    """Create a minimal in-memory/saved dataset for testing when no network."""
    lat_min, lon_min, lat_max, lon_max = bbox
    lats = np.linspace(lat_min, lat_max, 20)
    lons = np.linspace(lon_min, lon_max, 20)
    # 6-hour steps
    n_steps = forecast_days * 4
    times = np.array(
        [np.datetime64(start_time) + np.timedelta64(i * 6, "h") for i in range(n_steps)]
    )
    # Weak westward flow for demo
    u = np.zeros((len(times), len(lats), len(lons))) - 0.1
    v = np.zeros((len(times), len(lats), len(lons))) + 0.05
    ds = xr.Dataset(
        {
            "u": (("time", "lat", "lon"), u),
            "v": (("time", "lat", "lon"), v),
        },
        coords={"time": times, "lat": lats, "lon": lons},
    )
    return ds


def load_local(path: str) -> xr.Dataset:
    """Load a local NetCDF file and return xarray Dataset with u, v."""
    ds = xr.open_dataset(path)
    return ds


class CurrentProvider:
    """
    Wraps an xarray Dataset to provide get_currents(lat, lon, time) with interpolation.
    Handles forecast expiry: beyond last time step, returns last known field and sets flag.
    """

    def __init__(self, ds: xr.Dataset):
        self._ds = ds
        self._u_var = _find_var(ds, U_NAMES)
        self._v_var = _find_var(ds, V_NAMES)
        self._lat_var = _find_var(ds, LAT_NAMES) or "lat"
        self._lon_var = _find_var(ds, LON_NAMES) or "lon"
        self._time_var = _find_var(ds, TIME_NAMES) or "time"
        if not self._u_var or not self._v_var:
            raise ValueError("Dataset must contain u and v velocity variables")

    @property
    def time_range(self) -> Tuple[Optional[datetime], Optional[datetime]]:
        t = self._ds[self._time_var]
        if hasattr(t, "values") and len(t) > 0:
            t0 = t.values[0]
            t1 = t.values[-1]
            for i, v in enumerate([t0, t1]):
                if hasattr(v, "item"):
                    v = v.item()
                if isinstance(v, (int, float)):
                    v = np.datetime64(v, "ns")
                if i == 0:
                    t0 = v
                else:
                    t1 = v
            return (t0, t1)
        return (None, None)

    def get_currents(
        self, lat: float, lon: float, time: datetime
    ) -> Tuple[float, float, bool]:
        """
        Return (u, v) in m/s at (lat, lon, time). Interpolates in space and time.
        Third return value: forecast_expired (True if time is beyond dataset range).
        """
        u_var, v_var = self._u_var, self._v_var
        lat_var, lon_var, time_var = self._lat_var, self._lon_var, self._time_var
        ds = self._ds

        t_min, t_max = self.time_range
        forecast_expired = False
        time_np = np.datetime64(time, "ns")
        if t_min is not None and t_max is not None:
            def _to_np64(t):
                if isinstance(t, (int, float)):
                    return np.datetime64(t, "ns")
                return np.datetime64(t)
            t_min_np = _to_np64(t_min)
            t_max_np = _to_np64(t_max)
            if time_np < t_min_np:
                time_np = t_min_np
            if time_np > t_max_np:
                time_np = t_max_np
                forecast_expired = True

        try:
            u_da = ds[u_var]
            v_da = ds[v_var]
            if time_var in u_da.dims:
                u_val = float(u_da.interp(**{lat_var: lat, lon_var: lon, time_var: time_np}, method="linear").values)
                v_val = float(v_da.interp(**{lat_var: lat, lon_var: lon, time_var: time_np}, method="linear").values)
            else:
                u_val = float(u_da.interp(**{lat_var: lat, lon_var: lon}, method="linear").values)
                v_val = float(v_da.interp(**{lat_var: lat, lon_var: lon}, method="linear").values)
        except Exception:
            u_val, v_val = 0.0, 0.0

        if np.isnan(u_val):
            u_val = 0.0
        if np.isnan(v_val):
            v_val = 0.0
        return (float(u_val), float(v_val), forecast_expired)

    def get_dataset(self) -> xr.Dataset:
        return self._ds


def open_cached(
    bbox: Optional[Tuple[float, float, float, float]] = None,
    start_time: Optional[datetime] = None,
    forecast_days: Optional[int] = None,
    local_path: Optional[str] = None,
    data_dir: Optional[str] = None,
) -> CurrentProvider:
    """
    Open from local cache. If local_path given, use it. Otherwise look for a file in data_dir/DATA_DIR
    matching start_time and forecast_days, or fetch and open.
    """
    if local_path and os.path.isfile(local_path):
        ds = load_local(local_path)
        return CurrentProvider(ds)
    d = data_dir if data_dir is not None else DATA_DIR
    ensure_data_dir(d)
    if start_time is None:
        start_time = DEFAULT_START_TIME
    if forecast_days is None:
        forecast_days = DEFAULT_FORECAST_DAYS
    fname = f"currents_{start_time.strftime('%Y%m%d')}_{forecast_days}d.nc"
    path = os.path.join(d, fname)
    if os.path.isfile(path):
        ds = load_local(path)
        return CurrentProvider(ds)
    # No cache: fetch (or create synthetic) and open
    bbox = bbox or DEFAULT_BBOX
    fetch_and_save(bbox, start_time, forecast_days, local_path=path, data_dir=d)
    ds = load_local(path)
    return CurrentProvider(ds)
