"""
main.py — Blue Vector CLI entry point.

Usage examples:
    python main.py --mock favorable --out-plot route.png
    python main.py --mock favorable --compare
    python main.py --download-only
    python main.py --out-plot real_route.png
    python main.py --mock calm --start-lat 32 --start-lon -118 --target-lat 35 --target-lon -115
"""

import argparse
import logging
import sys
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

from blue_vector_claude.config import DEFAULT_BBOX, NETCDF_CACHE_PATH
from blue_vector_claude.mock_data import get_preset, PRESETS
from blue_vector_claude.data_loader import open_cached, fetch_and_save
from blue_vector_claude.wind_model import get_wind as parametric_wind
from blue_vector_claude.simulator import simulate_route
from blue_vector_claude.viz import plot_route, plot_comparison, animate_route
from blue_vector_claude.vessel_model import distance_km


class _WindWrapper:
    """Thin wrapper so wind_model.get_wind matches the provider interface."""
    def get_wind(self, lat, lon, time):
        return parametric_wind(lat, lon, time)


def _run_simulation(args, current_provider, label=""):
    wind = _WindWrapper() if not args.no_wind else None

    traj, times, days, energy, pct_saved, mode, sail_frac = simulate_route(
        start_lat=args.start_lat,
        start_lon=args.start_lon,
        target_lat=args.target_lat,
        target_lon=args.target_lon,
        max_days=args.max_days,
        current_provider=current_provider,
        wind_provider=wind,
        start_time=datetime.utcnow(),
        sail_motor_ok=True,
        propeller_motor_ok=True,
        turning_motors_working=2,
    )

    straight_km = distance_km(
        args.start_lat, args.start_lon,
        args.target_lat, args.target_lon,
    )
    arrived = days < args.max_days
    eta = times[-1].strftime("%Y-%m-%d %H:%M") if times else "—"

    print(f"\n{'='*55}")
    print(f"  Blue Vector Simulation  {label}")
    print(f"{'='*55}")
    print(f"  Mode            : {mode}")
    print(f"  Arrived         : {'YES' if arrived else 'NO (max_days reached)'}")
    print(f"  ETA             : {eta} UTC")
    print(f"  Trip duration   : {days:.2f} days")
    print(f"  Waypoints       : {len(traj)}")
    print(f"  Straight dist   : {straight_km:.1f} km")
    print(f"  Total energy    : {energy:.4f}")
    print(f"  Energy saved    : {pct_saved:+.1f}% vs straight-line baseline")
    print(f"  Sail fraction   : {sail_frac*100:.1f}%")
    print(f"{'='*55}\n")

    return traj, times, days, energy, pct_saved, mode, sail_frac


def main():
    parser = argparse.ArgumentParser(
        description="Blue Vector — ocean-current-aware vessel routing"
    )
    # Default route: Shanghai, China → Los Angeles, CA (~9000 km trans-Pacific)
    # North Pacific Current + westerlies carry vessels eastward on this route.
    parser.add_argument("--start-lat", type=float, default=31.2)
    parser.add_argument("--start-lon", type=float, default=121.5)
    parser.add_argument("--target-lat", type=float, default=34.05)
    parser.add_argument("--target-lon", type=float, default=-118.24)
    parser.add_argument("--max-days", type=float, default=90.0)
    parser.add_argument(
        "--mock", choices=list(PRESETS.keys()), default=None,
        help="Use mock current data (no network). Choices: " + ", ".join(PRESETS),
    )
    parser.add_argument("--no-wind", action="store_true",
                        help="Disable sail/wind model")
    parser.add_argument("--download-only", action="store_true",
                        help="Download RTOFS data and exit")
    parser.add_argument("--out-plot", type=str, default=None,
                        help="Save route map to this file")
    parser.add_argument("--compare", action="store_true",
                        help="Compare favorable vs unfavorable currents side-by-side")
    parser.add_argument("--animate", type=str, default=None,
                        help="Save sped-up route animation to this file (.mp4 or .gif)")
    args = parser.parse_args()

    # ── Download only ─────────────────────────────────────────────────────────
    if args.download_only:
        print("Downloading RTOFS data …")
        fetch_and_save(bbox=DEFAULT_BBOX, cache_path=NETCDF_CACHE_PATH)
        print(f"Saved → {NETCDF_CACHE_PATH}")
        return

    # ── Comparison mode ───────────────────────────────────────────────────────
    if args.compare:
        scenarios = []
        colors = {"favorable": "royalblue", "unfavorable": "darkorange"}
        for preset_name in ("favorable", "unfavorable"):
            provider = get_preset(preset_name)
            traj, times, days, energy, pct, mode, sf = _run_simulation(
                args, provider, label=f"[{preset_name}]"
            )
            scenarios.append(dict(
                label=preset_name.capitalize(),
                trajectory=traj,
                start_lat=args.start_lat, start_lon=args.start_lon,
                target_lat=args.target_lat, target_lon=args.target_lon,
                percent_saved=pct, total_days=days,
                color=colors.get(preset_name, "royalblue"),
            ))
        plot_comparison(scenarios, out_path=args.out_plot)
        return

    # ── Single simulation ─────────────────────────────────────────────────────
    if args.mock:
        provider = get_preset(args.mock)
        print(f"Using mock preset: {args.mock}")
    else:
        print("Loading RTOFS current data …")
        provider = open_cached(bbox=DEFAULT_BBOX, cache_path=NETCDF_CACHE_PATH)

    traj, times, days, energy, pct, mode, sf = _run_simulation(args, provider)

    energy_info = (
        f"Mode: {mode}  |  {days:.1f} days  |  Energy saved: {pct:+.1f}%\n"
        f"Sail fraction: {sf*100:.1f}%"
    )

    if args.out_plot:
        plot_route(
            trajectory=traj,
            start_lat=args.start_lat,
            start_lon=args.start_lon,
            target_lat=args.target_lat,
            target_lon=args.target_lon,
            current_provider=provider if not args.mock else None,
            plot_time=times[len(times) // 2] if times else None,
            out_path=args.out_plot,
            energy_info=energy_info,
        )

    if args.animate:
        animate_route(
            trajectory=traj,
            times=times,
            start_lat=args.start_lat,
            start_lon=args.start_lon,
            target_lat=args.target_lat,
            target_lon=args.target_lon,
            percent_saved=pct,
            total_days=days,
            current_provider=provider if not args.mock else None,
            out_path=args.animate,
        )

    if not args.out_plot and not args.animate:
        plot_route(
            trajectory=traj,
            start_lat=args.start_lat,
            start_lon=args.start_lon,
            target_lat=args.target_lat,
            target_lon=args.target_lon,
            current_provider=provider if not args.mock else None,
            plot_time=times[len(times) // 2] if times else None,
            out_path=None,
            energy_info=energy_info,
        )


if __name__ == "__main__":
    main()
