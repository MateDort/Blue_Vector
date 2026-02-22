"""
Visualization: vector field of currents, optimized route, straight-line route.
"""
from datetime import datetime
from typing import List, Tuple, Optional, Any

import matplotlib.pyplot as plt
import numpy as np


def plot_route(
    trajectory: List[Tuple[float, float]],
    start_lat: float,
    start_lon: float,
    target_lat: float,
    target_lon: float,
    current_provider: Optional[Any] = None,
    plot_time: Optional[datetime] = None,
    out_path: Optional[str] = None,
) -> None:
    """
    Plot optimized route, straight-line route, and optionally current vector field.
    """
    fig, ax = plt.subplots(figsize=(10, 8))

    lats = [p[0] for p in trajectory]
    lons = [p[1] for p in trajectory]

    # Current field at one time (if provider and time given and has dataset)
    if current_provider is not None and plot_time is not None:
        ds = current_provider.get_dataset()
        if ds is None:
            pass  # Mock provider has no grid to plot
        else:
            u_var = getattr(current_provider, "_u_var", "u")
            v_var = getattr(current_provider, "_v_var", "v")
            lat_var = getattr(current_provider, "_lat_var", "lat")
            lon_var = getattr(current_provider, "_lon_var", "lon")
            time_var = getattr(current_provider, "_time_var", "time")
            if u_var in ds and v_var in ds:
                try:
                    u_da = ds[u_var]
                    v_da = ds[v_var]
                    if time_var in u_da.dims:
                        u_slice = u_da.sel({time_var: plot_time}, method="nearest").squeeze()
                        v_slice = v_da.sel({time_var: plot_time}, method="nearest").squeeze()
                    else:
                        u_slice = u_da.squeeze()
                        v_slice = v_da.squeeze()
                    lon_vals = u_slice[lon_var].values
                    lat_vals = u_slice[lat_var].values
                    if lon_vals.ndim == 1 and lat_vals.ndim == 1:
                        LON, LAT = np.meshgrid(lon_vals, lat_vals)
                    else:
                        LON = lon_vals
                        LAT = lat_vals
                    U = np.asarray(u_slice.values)
                    V = np.asarray(v_slice.values)
                    step = max(1, min(U.shape[0], U.shape[1]) // 8)
                    if U.ndim == 2 and V.ndim == 2:
                        ax.quiver(
                            LON[::step, ::step], LAT[::step, ::step],
                            U[::step, ::step], V[::step, ::step],
                            scale=50, color="lightblue", alpha=0.7,
                        )
                except Exception:
                    pass

    # Straight-line route
    ax.plot(
        [start_lon, target_lon], [start_lat, target_lat],
        "k--", alpha=0.6, label="Straight-line route",
    )
    # Optimized route
    ax.plot(lons, lats, "b-o", markersize=2, label="Optimized route")
    ax.plot(start_lon, start_lat, "go", markersize=10, label="Start")
    ax.plot(target_lon, target_lat, "ro", markersize=10, label="Target")

    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.legend()
    ax.set_title("Ocean current routing: optimized vs straight-line")
    ax.axis("equal")
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    if out_path:
        plt.savefig(out_path, dpi=150)
        plt.close()
    else:
        plt.show()
