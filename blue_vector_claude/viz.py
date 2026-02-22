"""
viz.py — Visualise the optimised route vs the straight-line baseline.

Explain like you're 8:
  This file draws the map. It shows the path the boat took (blue curve)
  and the "shortest straight line" (red dashes) so you can see how much
  the route curved to ride the currents. Optional arrows show the ocean
  current direction at a point in time.
"""

import math
import subprocess
import sys
from datetime import datetime
from typing import List, Tuple, Optional

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches


def _match_lon(ref_lon: float, anchor_lon: float) -> float:
    """Shift ref_lon by ±360° increments until closest to anchor_lon."""
    out = ref_lon
    while out - anchor_lon > 180:
        out -= 360
    while anchor_lon - out > 180:
        out += 360
    return out


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km."""
    R = 6_371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin(math.radians(lat2 - lat1) / 2) ** 2
         + math.cos(phi1) * math.cos(phi2)
         * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _open_file(path: str) -> None:
    if sys.platform == "darwin":
        subprocess.Popen(["open", path])
    elif sys.platform.startswith("linux"):
        subprocess.Popen(["xdg-open", path])


def plot_route(
    trajectory: List[Tuple[float, float]],
    start_lat: float,
    start_lon: float,
    target_lat: float,
    target_lon: float,
    current_provider=None,
    plot_time: Optional[datetime] = None,
    out_path: Optional[str] = None,
    title: str = "Blue Vector — Optimised Route",
    energy_info: Optional[str] = None,
) -> None:
    """
    Plot the trajectory against the straight-line baseline.

    Args:
        trajectory     : list of (lat, lon) waypoints from simulate_route
        current_provider: CurrentProvider with get_dataset() for quiver (optional)
        plot_time      : datetime to sample current field for quiver (optional)
        out_path       : save figure here; if None, call plt.show()
        energy_info    : optional string printed in the plot subtitle
    """
    lats = [p[0] for p in trajectory]
    raw_lons = [p[1] for p in trajectory]

    # Unwrap longitudes: handles dateline crossing (e.g., Pacific routes
    # where lon goes 121 → 180 → 241 rather than jumping to -179)
    lons = list(np.degrees(np.unwrap(np.radians(raw_lons))))

    # Adjust start/target lon to the same extended-longitude convention
    # so markers land on the trajectory's axis range
    plot_start_lon = _match_lon(start_lon, lons[0]) if lons else start_lon
    plot_target_lon = _match_lon(target_lon, lons[-1]) if lons else target_lon

    fig, ax = plt.subplots(figsize=(12, 7))
    ax.set_facecolor("#d6eaf8")  # light ocean blue background

    # ── Current quiver ────────────────────────────────────────────────────────
    if current_provider is not None and plot_time is not None:
        ds = current_provider.get_dataset()
        if ds is not None:
            try:
                t_da = np.datetime64(plot_time.replace(tzinfo=None))
                import xarray as xr
                snap = ds.interp(time=xr.DataArray(t_da), method="linear")
                u_grid = snap["u_velocity"].values
                v_grid = snap["v_velocity"].values
                grid_lats = ds["lat"].values
                grid_lons = ds["lon"].values

                # Subsample so arrows don't crowd the plot
                step_lat = max(1, len(grid_lats) // 15)
                step_lon = max(1, len(grid_lons) // 15)
                sl = slice(None, None, step_lat)
                sl2 = slice(None, None, step_lon)

                lon_grid, lat_grid = np.meshgrid(grid_lons[sl2], grid_lats[sl])
                ax.quiver(
                    lon_grid, lat_grid,
                    u_grid[sl, sl2], v_grid[sl, sl2],
                    color="steelblue", alpha=0.35, scale=3,
                    width=0.002, label="Ocean current",
                )
            except Exception:
                pass  # quiver is optional; don't crash if it fails

    # ── Straight-line baseline ────────────────────────────────────────────────
    ax.plot(
        [plot_start_lon, plot_target_lon], [start_lat, target_lat],
        "--", color="tomato", linewidth=1.5, label="Straight-line baseline",
    )

    # ── Optimised trajectory ──────────────────────────────────────────────────
    ax.plot(
        lons, lats,
        "-o", color="royalblue", linewidth=2, markersize=3, label="Optimised route",
        zorder=5,
    )

    # ── Start / target markers ────────────────────────────────────────────────
    ax.scatter(plot_start_lon, start_lat, s=120, c="limegreen", zorder=6,
               edgecolors="black", linewidths=0.8, label="Start")
    ax.scatter(plot_target_lon, target_lat, s=120, c="red", zorder=6,
               edgecolors="black", linewidths=0.8, label="Target")

    # ── Labels & style ────────────────────────────────────────────────────────
    # Format x-axis as E/W longitude regardless of extended (>180) values
    import matplotlib.ticker as mticker
    def _lon_formatter(x, pos):
        x_norm = ((x + 180) % 360) - 180  # normalise to [-180, 180]
        if abs(x_norm) < 0.001:
            return "0°"
        if x_norm > 0:
            return f"{x_norm:.0f}°E"
        return f"{abs(x_norm):.0f}°W"
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(_lon_formatter))

    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude (°)")
    ax.set_title(title, fontsize=14, fontweight="bold")

    if energy_info:
        ax.text(
            0.02, 0.02, energy_info,
            transform=ax.transAxes,
            fontsize=9, verticalalignment="bottom",
            bbox=dict(boxstyle="round", facecolor="white", alpha=0.8),
        )

    ax.legend(loc="upper right", fontsize=9)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()

    if out_path:
        plt.savefig(out_path, dpi=150, bbox_inches="tight")
        print(f"Route map saved → {out_path}")
        _open_file(out_path)
    else:
        plt.show()

    plt.close(fig)


def plot_comparison(
    scenarios: list,
    out_path: Optional[str] = None,
) -> None:
    """
    Side-by-side comparison of multiple scenarios.

    Args:
        scenarios: list of dicts with keys:
            label, trajectory, start_lat, start_lon, target_lat, target_lon,
            percent_saved, total_days, color (optional)
    """
    n = len(scenarios)
    fig, axes = plt.subplots(1, n, figsize=(7 * n, 6), squeeze=False)

    for i, sc in enumerate(scenarios):
        ax = axes[0][i]
        ax.set_facecolor("#d6eaf8")

        lats = [p[0] for p in sc["trajectory"]]
        lons = [p[1] for p in sc["trajectory"]]
        color = sc.get("color", "royalblue")

        ax.plot([sc["start_lon"], sc["target_lon"]],
                [sc["start_lat"], sc["target_lat"]],
                "--", color="tomato", linewidth=1.5, label="Baseline")
        ax.plot(lons, lats, "-o", color=color, linewidth=2,
                markersize=3, label="Optimised", zorder=5)
        ax.scatter(sc["start_lon"], sc["start_lat"], s=100, c="limegreen",
                   zorder=6, edgecolors="black", linewidths=0.8)
        ax.scatter(sc["target_lon"], sc["target_lat"], s=100, c="red",
                   zorder=6, edgecolors="black", linewidths=0.8)

        label = sc.get("label", f"Scenario {i+1}")
        pct = sc.get("percent_saved", 0)
        days = sc.get("total_days", 0)
        ax.set_title(f"{label}\n{days:.1f} days | {pct:+.1f}% energy",
                     fontsize=11, fontweight="bold")
        ax.set_xlabel("Longitude (°)")
        ax.set_ylabel("Latitude (°)")
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)

    plt.suptitle("Blue Vector — Scenario Comparison", fontsize=14, fontweight="bold")
    plt.tight_layout()

    if out_path:
        plt.savefig(out_path, dpi=150, bbox_inches="tight")
        print(f"Comparison plot saved → {out_path}")
        _open_file(out_path)
    else:
        plt.show()

    plt.close(fig)


def animate_route(
    trajectory: List[Tuple[float, float]],
    times: list,
    start_lat: float,
    start_lon: float,
    target_lat: float,
    target_lon: float,
    percent_saved: float,
    total_days: float,
    current_provider=None,
    out_path: str = "route_animation.mp4",
    fps: int = 24,
    title: str = "Blue Vector — Optimised Route",
) -> None:
    """
    Render the pre-computed trajectory as a sped-up animation.

    Each frame advances one 6-hour simulation step. At 24 fps a 347-step
    trans-Pacific voyage plays back in ~14 seconds.

    Saves as MP4 (requires ffmpeg) or GIF (Pillow fallback) depending on
    the out_path extension.
    """
    from matplotlib.animation import FuncAnimation, PillowWriter
    try:
        from matplotlib.animation import FFMpegWriter
        _ffmpeg_ok = True
    except ImportError:
        _ffmpeg_ok = False

    import matplotlib.ticker as mticker

    lats = [p[0] for p in trajectory]
    raw_lons = [p[1] for p in trajectory]
    lons = list(np.degrees(np.unwrap(np.radians(raw_lons))))

    plot_start_lon = _match_lon(start_lon, lons[0]) if lons else start_lon
    plot_target_lon = _match_lon(target_lon, lons[-1]) if lons else target_lon
    n = len(trajectory)

    # ── Figure setup ──────────────────────────────────────────────────────────
    fig, ax = plt.subplots(figsize=(12, 7))
    ax.set_facecolor("#d6eaf8")

    # Fixed axis limits with padding
    all_lons = lons + [plot_start_lon, plot_target_lon]
    all_lats = lats + [start_lat, target_lat]
    ax.set_xlim(min(all_lons) - 4, max(all_lons) + 4)
    ax.set_ylim(min(all_lats) - 3, max(all_lats) + 3)

    # ── Static: current quiver (first RTOFS snapshot) ─────────────────────────
    if current_provider is not None:
        ds = current_provider.get_dataset()
        if ds is not None:
            try:
                snap = ds.isel(time=0)
                u_grid = snap["u_velocity"].squeeze().values
                v_grid = snap["v_velocity"].squeeze().values
                grid_lats = ds["lat"].values
                grid_lons = ds["lon"].values
                sl = slice(None, None, max(1, len(grid_lats) // 15))
                sl2 = slice(None, None, max(1, len(grid_lons) // 15))
                lon_g, lat_g = np.meshgrid(grid_lons[sl2], grid_lats[sl])
                ax.quiver(
                    lon_g, lat_g,
                    u_grid[sl, sl2], v_grid[sl, sl2],
                    color="steelblue", alpha=0.25, scale=3,
                    width=0.002, zorder=1,
                )
            except Exception:
                pass

    # ── Static: baseline, markers, ghost route ────────────────────────────────
    ax.plot(
        [plot_start_lon, plot_target_lon], [start_lat, target_lat],
        "--", color="tomato", linewidth=1.5, alpha=0.5,
        label="Straight-line baseline", zorder=2,
    )
    # Faint ghost of full route so viewer can see where boat is headed
    ax.plot(lons, lats, "-", color="royalblue", linewidth=1,
            alpha=0.12, zorder=3)
    ax.scatter(plot_start_lon, start_lat, s=130, c="limegreen",
               zorder=6, edgecolors="black", linewidths=0.8, label="Start (Shanghai)")
    ax.scatter(plot_target_lon, target_lat, s=130, c="red",
               zorder=6, edgecolors="black", linewidths=0.8, label="Target (Los Angeles)")

    # ── Dynamic elements ──────────────────────────────────────────────────────
    trail_line, = ax.plot([], [], "-", color="royalblue", linewidth=2.2, zorder=5)
    boat_dot,   = ax.plot([], [], "o", color="white", markersize=10, zorder=7,
                          markeredgecolor="#1a56cc", markeredgewidth=2.5)
    stats_text = ax.text(
        0.02, 0.03, "", transform=ax.transAxes,
        fontsize=10, verticalalignment="bottom",
        bbox=dict(boxstyle="round,pad=0.4", facecolor="white", alpha=0.88),
        zorder=8,
    )

    # ── Formatting ────────────────────────────────────────────────────────────
    def _lon_fmt(x, pos):
        x_n = ((x + 180) % 360) - 180
        if abs(x_n) < 0.001:
            return "0°"
        return f"{abs(x_n):.0f}°{'E' if x_n > 0 else 'W'}"

    ax.xaxis.set_major_formatter(mticker.FuncFormatter(_lon_fmt))
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude (°)")
    ax.set_title(title, fontsize=14, fontweight="bold")
    ax.legend(loc="upper right", fontsize=9)
    ax.grid(True, alpha=0.3)
    plt.tight_layout()

    t0 = times[0] if times else None

    # ── Frame update ──────────────────────────────────────────────────────────
    def update(i):
        trail_line.set_data(lons[:i + 1], lats[:i + 1])
        boat_dot.set_data([lons[i]], [lats[i]])

        if t0 is not None:
            elapsed = (times[i] - t0).total_seconds() / 86400
            dist_rem = _haversine_km(lats[i], raw_lons[i], target_lat, target_lon)
            date_str = times[i].strftime("%Y-%m-%d")

            if i == n - 1:
                stats_text.set_text(
                    f"ARRIVED   ·   {elapsed:.1f} days   ·   {date_str}\n"
                    f"Energy saved vs straight-line motor: {percent_saved:+.1f}%"
                )
            else:
                stats_text.set_text(
                    f"Day {elapsed:.1f}   ·   {dist_rem:,.0f} km remaining   ·   {date_str}"
                )

        return trail_line, boat_dot, stats_text

    anim = FuncAnimation(fig, update, frames=n, interval=1000 / fps, blit=True)

    # ── Save ──────────────────────────────────────────────────────────────────
    use_mp4 = out_path.lower().endswith(".mp4") and _ffmpeg_ok
    if use_mp4:
        writer = FFMpegWriter(fps=fps, bitrate=1200,
                              metadata={"title": "Blue Vector Route Animation"})
    else:
        writer = PillowWriter(fps=fps)

    print(f"Rendering {n} frames at {fps} fps → {out_path} …")
    anim.save(out_path, writer=writer, dpi=120)
    print(f"Animation saved → {out_path}")
    _open_file(out_path)
    plt.close(fig)
