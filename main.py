#!/usr/bin/env python3
"""
Blue Vector: ocean-current-aware routing. CLI: download data and/or run simulation.
"""
import argparse
import logging
import os
from datetime import datetime, timedelta

from config import (
    DATA_DIR,
    DEFAULT_BBOX,
    DEFAULT_START_TIME,
    DEFAULT_FORECAST_DAYS,
)
from data_loader import ensure_data_dir, fetch_and_save, open_cached
from simulator import simulate_route
from viz import plot_route

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def _scenario_label(percent_energy_saved: float) -> str:
    if percent_energy_saved >= 20:
        return "favorable current"
    if percent_energy_saved >= 0:
        return "moderate current"
    return "unfavorable current"


def main() -> None:
    p = argparse.ArgumentParser(description="Blue Vector: ocean-current routing")
    p.add_argument("--download-only", action="store_true", help="Only download/cache current data")
    p.add_argument("--bbox", nargs=4, type=float, metavar=("LAT_MIN", "LON_MIN", "LAT_MAX", "LON_MAX"),
                   default=None, help="Bounding box (default: North Atlantic)")
    p.add_argument("--start-time", type=str, default=None,
                   help="Start time YYYY-MM-DD (default: today UTC)")
    p.add_argument("--forecast-days", type=int, default=DEFAULT_FORECAST_DAYS,
                   help="Forecast duration in days")
    p.add_argument("--start-lat", type=float, default=35.0, help="Start latitude")
    p.add_argument("--start-lon", type=float, default=-70.0, help="Start longitude")
    p.add_argument("--target-lat", type=float, default=40.0, help="Target latitude")
    p.add_argument("--target-lon", type=float, default=-65.0, help="Target longitude")
    p.add_argument("--max-days", type=float, default=14.0, help="Max simulation days")
    p.add_argument("--out-plot", type=str, default=None, help="Save plot to path")
    p.add_argument("--data-dir", type=str, default=DATA_DIR, help="Data cache directory")
    p.add_argument("--motor-failed", action="store_true", help="Sail-only mode (no motor)")
    p.add_argument("--wind-out", action="store_true", help="Motor-only mode (no wind/sail)")
    p.add_argument("--emergency", action="store_true", help="Emergency to shore: minimize time only")
    args = p.parse_args()

    bbox = tuple(args.bbox) if args.bbox else DEFAULT_BBOX
    start_time = datetime.strptime(args.start_time, "%Y-%m-%d") if args.start_time else DEFAULT_START_TIME

    # 4 motors: 1 sail, 1 propeller, 2 turning
    sail_motor_ok = not args.wind_out
    propeller_motor_ok = not args.motor_failed
    turning_motors_working = 2 if not args.motor_failed else 0

    if args.download_only:
        ensure_data_dir(args.data_dir)
        path = fetch_and_save(bbox, start_time, args.forecast_days, data_dir=args.data_dir)
        logger.info("Data saved to %s. Run without --download-only to simulate.", path)
        return

    # Run simulation: use cached data (no network in simulate_route)
    provider = open_cached(
        bbox=bbox, start_time=start_time, forecast_days=args.forecast_days, data_dir=args.data_dir
    )
    trajectory, times, total_time_days, total_energy, percent_saved, mode, sail_fraction = simulate_route(
        args.start_lat, args.start_lon, args.target_lat, args.target_lon,
        args.max_days, provider, start_time=start_time,
        sail_motor_ok=sail_motor_ok,
        propeller_motor_ok=propeller_motor_ok,
        turning_motors_working=turning_motors_working,
        emergency_to_shore=args.emergency,
    )
    arrival_time = times[-1]
    scenario = _scenario_label(percent_saved)

    print("--- Results ---")
    print(f"Mode:             {mode}")
    print(f"Arrival time:     {arrival_time}")
    print(f"Total time:       {total_time_days:.2f} days")
    print(f"Propulsion energy: {total_energy:.2e} (arb. units)")
    print(f"Energy saved:     {percent_saved:.1f}% vs straight-line")
    if sail_motor_ok and sail_fraction > 0:
        print(f"Sail contribution: {sail_fraction*100:.1f}% of displacement")
    print(f"Scenario:         {scenario}")

    plot_time = times[len(times) // 2] if times else start_time
    plot_route(
        trajectory, args.start_lat, args.start_lon, args.target_lat, args.target_lon,
        current_provider=provider, plot_time=plot_time, out_path=args.out_plot,
    )
    if args.out_plot:
        print(f"Plot saved to {args.out_plot}")


if __name__ == "__main__":
    main()
