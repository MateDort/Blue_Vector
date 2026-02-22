"""
showcase.py — Live proof that Blue Vector uses real NOAA ocean current data.

Hits the NOAA RTOFS OPeNDAP endpoint directly, parses the response,
and renders a coloured terminal table showing actual Pacific current
velocities — the same numbers the routing algorithm reads.

Usage:
    python showcase.py
"""

import math
import time
import urllib.request
from datetime import datetime, timezone

# ── ANSI colours ──────────────────────────────────────────────────────────────
RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
CYAN   = "\033[96m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
BLUE   = "\033[94m"
WHITE  = "\033[97m"
ORANGE = "\033[38;5;208m"

FILL_VALUE = 1.26765e30


def _banner():
    print()
    print(f"{CYAN}{BOLD}╔{'═'*62}╗{RESET}")
    print(f"{CYAN}{BOLD}║{'BLUE VECTOR — LIVE NOAA OCEAN CURRENT FETCH':^62}║{RESET}")
    print(f"{CYAN}{BOLD}╚{'═'*62}╝{RESET}")
    print()


def _fetch_slice(date_str: str, lat_idx: int, lon_start: int,
                 lon_end: int, lon_step: int) -> dict:
    """
    Fetch a single row of u_velocity + v_velocity via RTOFS OPeNDAP ASCII.
    Returns dict with keys: lats, lons, u, v, elapsed_ms
    """
    base = (
        f"https://nomads.ncep.noaa.gov/dods/rtofs/"
        f"rtofs_global{date_str}/rtofs_glo_2ds_nowcast_hrly_prog.ascii"
    )
    lat_sel  = f"%5B{lat_idx}:1:{lat_idx}%5D"
    lon_sel  = f"%5B{lon_start}:{lon_step}:{lon_end}%5D"
    time_lev = "%5B0%5D%5B0%5D"
    url = f"{base}?u_velocity{time_lev}{lat_sel}{lon_sel},v_velocity{time_lev}{lat_sel}{lon_sel}"

    t0 = time.time()
    with urllib.request.urlopen(url, timeout=30) as resp:
        raw = resp.read().decode()
    elapsed_ms = (time.time() - t0) * 1000

    # Parse ASCII OPeNDAP response.
    # Format:
    #   u_velocity, [1][1][1][N]        ← header
    #   [0][0][0], val, val, ...        ← data row  (starts with "[")
    #   lat, [1]                        ← coord header
    #   34.995                          ← coord values (plain numbers, no "[")
    #   lon, [N]
    #   150.07, 152.57, ...
    u_vals, v_vals, lats_out, lons_out = [], [], [], []
    section = None
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("u_velocity"):
            section = "u"
        elif line.startswith("v_velocity"):
            section = "v"
        elif line.startswith("lat,"):
            section = "lat"
        elif line.startswith("lon,"):
            section = "lon"
        elif line.startswith("time,") or line.startswith("lev,"):
            section = "skip"
        elif section in ("u", "v") and line.startswith("["):
            # e.g. "[0][0][0], -0.04, 0.88, ..."
            nums = [float(x) for x in line.split(",")[1:] if x.strip()]
            if section == "u":
                u_vals.extend(nums)
            else:
                v_vals.extend(nums)
        elif section in ("lat", "lon") and not line.startswith("["):
            # plain number line: "34.995" or "150.07, 152.57, ..."
            nums = [float(x) for x in line.split(",") if x.strip()]
            if section == "lat":
                lats_out.extend(nums)
            else:
                lons_out.extend(nums)

    return dict(lats=lats_out, lons=lons_out, u=u_vals, v=v_vals,
                elapsed_ms=elapsed_ms, url=url)


def _direction_arrow(bearing_deg: float) -> str:
    arrows = ["↑", "↗", "→", "↘", "↓", "↙", "←", "↖"]
    return arrows[round(bearing_deg / 45) % 8]


def _current_bar(speed: float, max_speed: float = 1.5, width: int = 12) -> str:
    filled = round((speed / max_speed) * width)
    filled = min(filled, width)
    bar = "█" * filled + "░" * (width - filled)
    if speed > 0.8:
        return f"{RED}{bar}{RESET}"
    elif speed > 0.35:
        return f"{YELLOW}{bar}{RESET}"
    else:
        return f"{DIM}{bar}{RESET}"


def main():
    _banner()

    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    now_utc  = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # ── Connection info ────────────────────────────────────────────────────────
    print(f"  {BOLD}Source   {RESET}: NOAA RTOFS (Real-Time Ocean Forecast System)")
    print(f"  {BOLD}Endpoint {RESET}: OPeNDAP .ascii (public, no API key)")
    print(f"  {BOLD}Run date {RESET}: {date_str}  |  queried at {now_utc}")
    print(f"  {BOLD}Variable {RESET}: u_velocity, v_velocity (ocean surface, m/s)")
    print()

    # Sample 1 — Kuroshio Extension (35°N, 150–180°E)
    # lat index for 35°N  ≈ (35 + 90) / 0.0833 = 1500
    # lon index for 150°E ≈ (150 - 74.16) / 0.0833 = 911
    # lon index for 180°E ≈ (180 - 74.16) / 0.0833 = 1271
    print(f"  {CYAN}Fetching row 1:{RESET} 35°N across the Kuroshio Extension  "
          f"(150–180°E) …")
    r1 = _fetch_slice(date_str, lat_idx=1500,
                      lon_start=911, lon_end=1271, lon_step=30)

    # Sample 2 — North Pacific Current (42°N, 170°E–220°E / mid-ocean)
    # lat index for 42°N  ≈ (42 + 90) / 0.0833 = 1584
    # lon index for 170°E ≈ (170 - 74.16) / 0.0833 = 1151
    # lon index for 220°E ≈ (220 - 74.16) / 0.0833 = 1751
    print(f"  {CYAN}Fetching row 2:{RESET} 42°N across the North Pacific Current "
          f"(170–220°E) …")
    r2 = _fetch_slice(date_str, lat_idx=1584,
                      lon_start=1151, lon_end=1751, lon_step=40)
    print()

    # ── Table ─────────────────────────────────────────────────────────────────
    col = f"{DIM}│{RESET}"
    hdr_lat = f"{BOLD}{CYAN}"

    def print_row(lat_label, result):
        print(f"  {hdr_lat}{'Lon':>9}  {'u → E (m/s)':>12}  {'v ↑ N (m/s)':>12}  "
              f"{'Speed':>8}  {'Dir':>3}  {'Intensity':<14}  Note{RESET}")
        print(f"  {'─'*80}")
        for lon, ui, vi in zip(result["lons"], result["u"], result["v"]):
            if abs(ui) > 1e20 or abs(vi) > 1e20:
                print(f"  {lon:>8.1f}°E  {'— land / ice mask —':>48}")
                continue
            speed   = math.sqrt(ui**2 + vi**2)
            bearing = math.degrees(math.atan2(ui, vi)) % 360
            arrow   = _direction_arrow(bearing)
            bar     = _current_bar(speed)

            if speed > 0.8:
                note  = f"{RED}{BOLD}◀ KUROSHIO / NPC CORE{RESET}"
                color = RED
            elif speed > 0.35:
                note  = f"{YELLOW}moderate{RESET}"
                color = YELLOW
            else:
                note  = f"{DIM}weak{RESET}"
                color = DIM + WHITE

            print(f"  {color}{lon:>8.1f}°E{RESET}  "
                  f"{ui:>+12.3f}  {vi:>+12.3f}  "
                  f"{speed:>7.3f}m/s  {arrow:>3}  {bar}  {note}")
        print()

    print(f"  {BOLD}{CYAN}{'─'*36} ROW 1: lat ≈ 35.0°N {'─'*25}{RESET}")
    print_row("35°N", r1)

    print(f"  {BOLD}{CYAN}{'─'*36} ROW 2: lat ≈ 42.0°N {'─'*25}{RESET}")
    print_row("42°N", r2)

    # ── Summary ───────────────────────────────────────────────────────────────
    all_points = [
        (math.sqrt(u**2 + v**2), lon)
        for lon, u, v in zip(r1["lons"] + r2["lons"],
                             r1["u"]   + r2["u"],
                             r1["v"]   + r2["v"])
        if abs(u) < 1e20 and abs(v) < 1e20
    ]
    peak, peak_lon = max(all_points, key=lambda x: x[0])

    print(f"  {BOLD}Peak current detected:{RESET}  "
          f"{RED}{BOLD}{peak:.3f} m/s  ({peak * 1.944:.2f} knots){RESET}"
          f"  at lon {peak_lon:.1f}°E")
    print(f"  {DIM}At that speed the vessel gains {peak * 21600 / 1000:.1f} km per 6-hour step for free.{RESET}")
    print()
    print(f"  {GREEN}{BOLD}✓{RESET}  Data fetched in "
          f"{r1['elapsed_ms']:.0f} ms + {r2['elapsed_ms']:.0f} ms  "
          f"— same endpoint Blue Vector reads on every run.")
    print(f"  {GREEN}{BOLD}✓{RESET}  No API key.  No mock.  Direct from NOAA servers.")
    print()


if __name__ == "__main__":
    main()
