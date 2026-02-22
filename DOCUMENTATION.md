# Blue Vector — How Everything Works

This document explains **every file**, **every important calculation**, and **code examples**, in plain language. There’s also a **“Explain like you’re 8”** section for each part.

---

## Table of Contents

1. [Big picture (what Blue Vector does)](#1-big-picture)
2. [config.py — All the knobs](#2-configpy)
3. [data_loader.py — Getting ocean current data](#3-data_loaderpy)
4. [vessel_model.py — How the boat moves](#4-vessel_modelpy)
5. [router.py — Choosing which way to steer](#5-routerpy)
6. [simulator.py — Running the full trip](#6-simulatorpy)
7. [wind_model.py — Wind for the sail](#7-wind_modelpy)
8. [viz.py — Drawing the map](#8-vizpy)
9. [mock_data.py — Fake currents for demos](#9-mock_datapy)
10. [main.py — Command-line entry](#10-mainpy)
11. [server.py — Web API](#11-serverpy)
12. [Math reference](#12-math-reference)
13. [Code examples](#13-code-examples)

---

## 1. Big picture

**What Blue Vector does:**  
It plans a boat route that **uses ocean currents and wind** instead of fighting them. The motor is mainly for **steering** (hopping into good “lanes”), not for pushing straight through the water.

**Explain like you’re 8:**  
Imagine a river with fast and slow lanes. Blue Vector is like a smart driver that chooses which lane to be in so the water (and wind) push the boat toward the goal. The engine is used a little bit to change lanes; the rest is free ride.

---

## 2. config.py

**What it does:**  
Holds all **default settings**: map area, time step, how far ahead we plan, how much we care about time vs distance vs energy, vessel limits, and motor/wind options.

**How it works:**  
Other files `import` these values. Nothing runs here; it’s just a single place to change behavior.

**Important numbers:**

| Name | Meaning | Example |
|------|--------|--------|
| `TIMESTEP_HOURS` | How many hours per simulation step | 6 → we move the boat every 6 hours |
| `MAX_STEERING_SPEED_MS` | Max steering speed (m/s) | 0.3 |
| `HORIZON_DAYS` | How many days we “look ahead” when choosing direction | 5 |
| `ANGLE_RANGE_DEG` | Steering range left/right of “toward target” | 45° |
| `ALPHA`, `BETA` | Weights for time and distance in the cost | 1.0, 1.0 |
| `SAIL_EFFICIENCY` | How much of wind speed becomes boat movement | 0.35 |

**Explain like you’re 8:**  
This file is like the **rules of the game**: how big each step is, how far we’re allowed to look ahead, and how much we care about saving energy vs getting there fast.

**Code example:**

```python
from config import TIMESTEP_HOURS, DEFAULT_BBOX, ALPHA, BETA

# Use in your code
step_hours = TIMESTEP_HOURS  # 6
lat_min, lon_min, lat_max, lon_max = DEFAULT_BBOX
cost = ALPHA * time_days + BETA * distance_km
```

---

## 3. data_loader.py

**What it does:**  
Gets **ocean current data** (how fast the water moves east `u` and north `v` at each point and time). It can **download** from NOAA (OPeNDAP) or **read from a saved NetCDF file**. It also builds a **synthetic** (fake) dataset when there’s no network.

**How it works:**

1. **Fetch:** Tries to open a NOAA RTOFS URL, subset by bounding box, save as NetCDF.
2. **If that fails:** Builds a small synthetic grid (e.g. weak westward flow) and saves it.
3. **CurrentProvider:** Wraps the dataset and exposes `get_currents(lat, lon, time)` with **linear interpolation** in space and time.
4. **Forecast expiry:** If you ask for a time **after** the last time in the data, it uses the last known field and marks `forecast_expired = True`.

**Math (interpolation):**  
We don’t write the interpolation ourselves; `xarray`’s `.interp(lat=..., lon=..., time=..., method="linear")` does it. So at any `(lat, lon, time)` we get a smooth blend of the nearest grid values.

**Explain like you’re 8:**  
This file is the **weather report for the ocean**. It either gets real data from the internet or makes up a simple “river” so we can still play. When we ask “how fast is the water moving *here*, *now*?”, this file answers.

**Code example:**

```python
from data_loader import open_cached, CurrentProvider
from datetime import datetime

# Open cached data (or download/synthetic if missing)
provider = open_cached(
    bbox=(25, -80, 45, -60),
    start_time=datetime(2025, 2, 1),
    forecast_days=7,
)

# Get current at one point and time (m/s east, m/s north, and "is forecast expired?")
u, v, expired = provider.get_currents(35.0, -70.0, datetime(2025, 2, 3, 12))
print(f"Current: east={u} m/s, north={v} m/s, expired={expired}")
```

---

## 4. vessel_model.py

**What it does:**  
Defines **how the boat moves in one time step**: current + sail + steering. It also has helpers: bearing to target, distance, “is the current good or bad?”, and baseline energy for a straight-line trip.

**Math (the important parts):**

### 4.1 One time step

- **Current:**  
  - `dx_current = u_ms * DT_SECONDS`,  
  - `dy_current = v_ms * DT_SECONDS`  
  (distance = speed × time.)

- **Sail (when sail motor OK and wind given):**  
  - `dx_sail = sail_efficiency * u_wind_ms * DT_SECONDS`  
  - `dy_sail = sail_efficiency * v_wind_ms * DT_SECONDS`  
  So a fraction of the wind velocity is turned into displacement.

- **Steering (motor):**  
  - Effective steering speed depends on propeller + turning motors (0, 1, or 2 working → 0, half, or full).  
  - `dx_steer = mag * cos(angle_rad) * DT_SECONDS`  
  - `dy_steer = mag * sin(angle_rad) * DT_SECONDS`  
  Angle is in degrees, converted to radians for cos/sin.

- **New position:**  
  - Total: `dx_tot = dx_current + dx_sail + dx_steer`, same for `dy_tot`.  
  - Convert `(dx_tot, dy_tot)` from meters to latitude/longitude change (see below), then  
  - `new_lat = lat + dlat`, `new_lon = lon + dlon`.

### 4.2 Meters ↔ degrees

- **Meters to degrees:**  
  - 1° latitude ≈ 111,320 m (constant).  
  - 1° longitude ≈ 111,320 × cos(lat) m (shorter near poles).  
  - So: `dlat = dy_m / 111320`, `dlon = dx_m / (111320 * cos(lat))`.

### 4.3 Propulsion energy (one step)

- `steering_speed_ms = sqrt(dx_steer² + dy_steer²) / DT_SECONDS`  
- `propulsion_energy_step = steering_speed_ms² * DT_SECONDS`  
So energy is proportional to **speed² × time** (like drag / power).

### 4.4 Bearing (angle to target)

- From `(lat1, lon1)` to `(lat2, lon2)`: use spherical formula with `atan2` so 0° = North, 90° = East.  
- Code uses radians for lat/lon and converts back to degrees.

### 4.5 Current favorability

- **Idea:** How much does the current (u, v) push us **toward** the target?  
- Unit vector toward target: `(ex, ey)` from bearing (east = sin(bearing), north = cos(bearing)).  
- Speed of current: `speed = sqrt(u² + v²) + tiny`.  
- **Favorability** = dot product of (u,v) with (ex,ey), divided by speed → value in **[-1, 1]**.  
  - 1 = current straight toward target, -1 = straight away, 0 = perpendicular.

### 4.6 Haversine distance

- Standard formula for distance on a sphere:  
  - `a = sin²(Δφ/2) + cos(φ1) cos(φ2) sin²(Δλ/2)`  
  - `c = 2 atan2(√a, √(1−a))`  
  - `distance_m = EARTH_RADIUS_M * c`  
  Then converted to km.

### 4.7 Straight-line baseline energy

- Straight line at constant speed `v`:  
  - `time = distance_m / v`  
  - `energy = v² * time = v² * (distance_m / v) = v * distance_m`  
  (In the code it’s implemented as `speed² * time_seconds`.)

**Explain like you’re 8:**  
This file is the **rulebook for one move**: in 6 hours, the boat is carried by the current, pushed a bit by the sail (if wind and sail motor work), and pushed a bit by the motor (steering). We also measure “is the current helping or hurting?” and how far we are from the goal.

**Code example:**

```python
from vessel_model import step, bearing_deg, distance_km, current_favorability, straight_line_energy_km

# One 6-hour step: start (35, -70), current (0.1 m/s east, 0.05 m/s north), steer 10° right of north
new_lat, new_lon, dx_steer, dy_steer, energy, dx_sail, dy_sail = step(
    35.0, -70.0,
    u_ms=0.1, v_ms=0.05,
    steering_angle_deg=10.0,
    u_wind_ms=2.0, v_wind_ms=0.0,
    sail_efficiency=0.35,
    sail_motor_ok=True,
    propeller_motor_ok=True,
    turning_motors_working=2,
)
print(f"New position: ({new_lat}, {new_lon}), energy this step: {energy}")

# Bearing from A to B (degrees)
b = bearing_deg(35, -70, 40, -65)
print(f"Bearing to target: {b}°")

# Distance in km
d_km = distance_km(35, -70, 40, -65)
print(f"Distance: {d_km} km")

# How good is this current? (-1 to 1)
fav = current_favorability(35, -70, 40, -65, 0.1, 0.05)
print(f"Current favorability: {fav}")

# Baseline: straight line at 0.3 m/s
time_s, baseline_energy = straight_line_energy_km(d_km, speed_ms=0.3)
print(f"Straight-line: {time_s/86400:.2f} days, energy {baseline_energy}")
```

---

## 5. router.py

**What it does:**  
At each step, the **router** decides **which steering angle** to use. It uses a **receding horizon**: try many angles, simulate forward for several days, and pick the angle that gives the **lowest cost**. The cost includes energy (with “save propeller in good current” and “penalize bad current”), time, and distance.

**How it works:**

1. **choose_steering(...)**  
   - Computes bearing to target and converts to a “steering” angle.  
   - Builds a list of angles: `bearing ± angle_range` in steps of `angle_step`.  
   - If forecast is expired, uses a **smaller** angle range (`FORECAST_EXPIRED_ANGLE_RANGE_DEG`).  
   - For each candidate angle, calls **\_simulate_forward** for `HORIZON_STEPS` (e.g. 5 days × 4 steps/day = 20 steps).  
   - Returns the angle with **smallest cost**.

2. **_simulate_forward(...)**  
   - For each step: get currents and wind, call **vessel_model.step**, accumulate energy and cost terms.  
   - **Cost terms:**  
     - **Energy term:** `energy * (1 + PROPELLER_SAVE_IN_GOOD_CURRENT_WEIGHT * max(0, favorability))` when not emergency → using propeller in a good current is penalized (save it for lane changes).  
     - **Bad current penalty:** `BAD_CURRENT_PENALTY_WEIGHT * max(0, -favorability)` → being in a bad current adds cost so we prefer steering into a better one.  
     - **Time:** `alpha * time_days`.  
     - **Distance:** `beta * distance_km`.  
     - **Latitude penalty:** optional penalty for going too far south on eastbound routes (trade-wind trap).  
   - If we get within **DISTANCE_TOLERANCE_KM** of target, we return early with that cost.  
   - **Emergency mode:** use a much larger alpha (EMERGENCY_TIME_ONLY_ALPHA) so we mostly minimize time.

**Math (cost formula):**

- Normal (no emergency):  
  `cost = cost_energy_term + cost_bad_current + α * time_days + β * dist_km + lat_penalty`  
- Emergency:  
  `cost = α_emergency * time_days + β * dist_km + lat_penalty`  
  (energy and bad-current terms not weighted for saving propeller.)

**Explain like you’re 8:**  
The router is the **brain** that says: “If I turn this way, I’ll use less gas and get pushed by the good current; if I turn that way, I’ll fight the current.” It tries lots of directions in its head for the next few days and picks the best one.

**Code example:**

```python
from router import choose_steering
from datetime import datetime

def my_get_currents(lat, lon, t):
    # Your provider
    return (0.1, 0.05, False)

angle, cost = choose_steering(
    lat=35.0, lon=-70.0,
    target_lat=40.0, target_lon=-65.0,
    current_time=datetime.utcnow(),
    get_currents=my_get_currents,
    forecast_expired=False,
)
print(f"Best steering angle: {angle}°, cost: {cost}")
```

---

## 6. simulator.py

**What it does:**  
Runs the **full route** from start to target: at each 6-hour step it calls the **router** to get the best steering angle, then **vessel_model.step** to move the boat. It stops when within **DISTANCE_TOLERANCE_KM** or when **max_days** is reached. It returns the **trajectory**, **times**, **total time**, **total propulsion energy**, **percent energy saved** vs straight-line, **mode** (combined / motor_only / sail_only / etc.), and **sail_fraction** (how much of displacement came from sail).

**How it works:**

1. Resolve **4 motors**: sail, propeller, 2× turning. From that we get `motor_ok`, `wind_ok`, `sail_eff`, and `get_wind_fn`.  
2. Determine **mode**: emergency_to_shore, combined, propeller_only, sail_only, or drift_only.  
3. Loop: at current (lat, lon) and time, call **choose_steering**, then **step**; append new position and time; accumulate energy and sail displacement.  
4. **Percent saved:**  
   - Baseline = straight_line_energy_km(straight_dist_km).  
   - If motor used: `percent_saved = (1 - total_energy / baseline_energy) * 100`.  
   - If no motor (sail only): 100% “saved”; if no comparison possible, 0%.

**Explain like you’re 8:**  
The simulator is the **full game**: start at A, and every 6 hours ask the router “which way?”, move the boat, and repeat until we reach B or run out of time. At the end it tells you how long it took and how much energy you saved compared to going in a straight line with the motor.

**Code example:**

```python
from simulator import simulate_route
from data_loader import open_cached
from datetime import datetime

provider = open_cached()  # or MockCurrentProvider
trajectory, times, total_days, total_energy, percent_saved, mode, sail_fraction = simulate_route(
    start_lat=35.0, start_lon=-70.0,
    target_lat=40.0, target_lon=-65.0,
    max_days=14.0,
    current_provider=provider,
    start_time=datetime.utcnow(),
    sail_motor_ok=True,
    propeller_motor_ok=True,
    turning_motors_working=2,
)
print(f"Mode: {mode}, Time: {total_days:.2f} days, Energy saved: {percent_saved:.1f}%, Sail: {sail_fraction*100:.1f}%")
```

---

## 7. wind_model.py

**What it does:**  
Simple **parametric wind**: by **latitude** and **month** it returns (u_wind, v_wind) in m/s (east, north). Used for sail-assisted routing and sail-only when the motor is out.

**How it works:**

- **Trade winds** (lat &lt; 27°): fixed westward, e.g. `u = -4 m/s`, `v = 0`.  
- **Westerlies** (30°–45°N): eastward, stronger in winter (Nov–Mar), weaker in summer (Jun–Aug).  
- **Transition** (27°–30°): linear blend between trade and westerly.  
- **Above 45°N:** weaker, variable (e.g. 2 m/s winter, 0.5 m/s summer).

**Math:**  
Just if/else and one blend: `u = (1-t)*TRADE_U + t*WESTERLY_U` with `t = (lat - 27) / (30 - 27)` in the transition band.

**Explain like you’re 8:**  
Wind is like a **fixed pattern on the map**: near the equator it blows west; in the middle latitudes it blows east, and stronger in winter. The file has no grid; it’s just “at this latitude and month, wind is this.”

**Code example:**

```python
from wind_model import get_wind
from datetime import datetime

u, v = get_wind(lat=35.0, lon=-70.0, time=datetime(2025, 2, 15))
print(f"Wind: east={u} m/s, north={v} m/s")
```

---

## 8. viz.py

**What it does:**  
**Plots** the optimized route and the straight-line route on a map. Optionally draws the **current vector field** (arrows) at one time slice from the current provider’s dataset.

**How it works:**  
Uses **matplotlib**: one figure, scatter/plot trajectory, plot start (green) and target (red), dashed straight line. If the provider has a dataset with u/v and lat/lon/time, it takes a slice at `plot_time`, builds a 2D grid, and draws quiver arrows (subsampled so it’s readable).

**Explain like you’re 8:**  
This file **draws the map** with the path the boat took and the “shortest line” so you can see how much the route curved to use currents.

**Code example:**

```python
from viz import plot_route
from datetime import datetime

plot_route(
    trajectory=[(35, -70), (36, -69), (40, -65)],
    start_lat=35, start_lon=-70,
    target_lat=40, target_lon=-65,
    current_provider=provider,
    plot_time=datetime(2025, 2, 5),
    out_path="route.png",
)
```

---

## 9. mock_data.py

**What it does:**  
Provides **mock** current data for demos and the web app: no NetCDF, just constant (u, v) or a small grid with nearest-neighbor lookup. Presets: **favorable** (eastward), **unfavorable** (westward), **cross** (e.g. northward), **calm** (weak).

**How it works:**  
`MockCurrentProvider.get_currents(lat, lon, time)` returns either fixed (u, v) or the (u, v) of the nearest grid point. `get_dataset()` returns `None` so the viz won’t try to plot a grid.

**Explain like you’re 8:**  
When we don’t have real ocean data, we pretend the whole ocean is moving one way (or calm). That way we can still run the same game and compare “good current” vs “bad current.”

**Code example:**

```python
from mock_data import MockCurrentProvider, preset_favorable_eastbound, preset_unfavorable_westbound

provider = preset_favorable_eastbound()
u, v, _ = provider.get_currents(35, -70, None)
print(f"Favorable: u={u}, v={v}")

custom = MockCurrentProvider(u_ms=0.1, v_ms=-0.02)
```

---

## 10. main.py

**What it does:**  
**Command-line entry**: parse arguments, optionally only **download** data, or **run simulation** with cached data and **plot** results. Handles `--motor-failed`, `--wind-out`, `--emergency`, etc., and maps them to sail/propeller/turning flags for the simulator.

**How it works:**

1. Parse CLI (bbox, start/target, max_days, out_plot, motor_failed, wind_out, emergency, …).  
2. If `--download-only`: ensure data dir, call **fetch_and_save**, exit.  
3. Otherwise: **open_cached** → get provider, then **simulate_route** with the right motor flags.  
4. Print results (mode, arrival time, total time, energy, % saved, sail fraction, scenario label).  
5. Call **viz.plot_route** (with optional out_path).

**Explain like you’re 8:**  
This is the **remote control**: you type commands like “download data only” or “run the trip and save the map.” It then runs the simulator and drawing.

**Code example:**

```bash
# Download data only
python main.py --download-only

# Run simulation, save map
python main.py --out-plot route.png

# Sail only (motor failed)
python main.py --motor-failed

# Motor only (no wind/sail)
python main.py --wind-out
```

---

## 11. server.py

**What it does:**  
**FastAPI** server for the web app: **POST /simulate** runs the same routing algorithm (with mocked or real current data) and returns trajectory, times, total_days, energy, percent_saved, mode, sail_fraction. Also **GET /health** and **GET /ensure_data** (to pre-download real Pacific data).

**How it works:**  
Request body specifies start/target, max_days, mode (combined / motor_only / sail_only), scenario (favorable / unfavorable / cross / calm) or custom (u, v) or **use_real_data**. Server picks **CurrentProvider** (mock preset, custom MockCurrentProvider, or **open_cached** for Pacific), then calls **simulate_route** and returns JSON.

**Explain like you’re 8:**  
The server is the **play button** for the website: when you click “Run simulation,” the browser asks the server “run the trip with these settings,” and the server runs the same game and sends back the path and stats.

**Code example (calling the API):**

```bash
curl -X POST http://localhost:8000/simulate \
  -H "Content-Type: application/json" \
  -d '{"start_lat":32,"start_lon":-120,"target_lat":35,"target_lon":-115,"scenario":"favorable","mode":"combined"}'
```

---

## 12. Math reference

### 12.1 Position update (one step)

- **DT_SECONDS** = `TIMESTEP_HOURS * 3600` (e.g. 6*3600 = 21600 s).  
- **Current:**  
  - `dx_current = u_ms * DT_SECONDS`,  
  - `dy_current = v_ms * DT_SECONDS`.  
- **Sail:**  
  - `dx_sail = sail_efficiency * u_wind * DT_SECONDS`,  
  - `dy_sail = sail_efficiency * v_wind * DT_SECONDS`.  
- **Steering:**  
  - `mag = (turning_motors_working/2) * MAX_STEERING_SPEED_MS` (capped),  
  - `dx_steer = mag * cos(angle_rad) * DT_SECONDS`,  
  - `dy_steer = mag * sin(angle_rad) * DT_SECONDS`.  
- **Total:**  
  - `dx_tot = dx_current + dx_sail + dx_steer`,  
  - `dy_tot = dy_current + dy_sail + dy_steer`.  
- **Meters → degrees:**  
  - `m_per_deg_lat = 111320`,  
  - `m_per_deg_lon = 111320 * cos(lat_rad)`,  
  - `dlat = dy_tot / m_per_deg_lat`,  
  - `dlon = dx_tot / m_per_deg_lon`.

### 12.2 Propulsion energy (one step)

- `v_steer = sqrt(dx_steer² + dy_steer²) / DT_SECONDS`  
- `E_step = v_steer² * DT_SECONDS`

### 12.3 Current favorability

- Bearing from boat to target: `b` (degrees).  
- Unit vector toward target (east, north):  
  - `ex = sin(b°)`,  
  - `ey = cos(b°)`.  
- Speed of current: `s = sqrt(u² + v²) + ε`.  
- **Favorability** = `(u*ex + v*ey) / s` ∈ [-1, 1].

### 12.4 Haversine distance (km)

- `φ1, φ2` = lat in radians, `Δφ = φ2−φ1`, `Δλ = lon2−lon1` in radians.  
- `a = sin²(Δφ/2) + cos(φ1)cos(φ2)sin²(Δλ/2)`  
- `c = 2 atan2(√a, √(1−a))`  
- `distance_km = (EARTH_RADIUS_M * c) / 1000`

### 12.5 Straight-line baseline

- `time_s = distance_m / speed_ms`  
- `energy = speed_ms² * time_s`

### 12.6 Router cost (conceptual)

- **cost_energy_term:** sum over steps of  
  - `energy_step * (1 + PROPELLER_SAVE_IN_GOOD_CURRENT_WEIGHT * max(0, favorability))`  
  (when not emergency and steering available).  
- **cost_bad_current:** sum of  
  - `BAD_CURRENT_PENALTY_WEIGHT * max(0, -favorability)`.  
- **cost** = cost_energy_term + cost_bad_current + α×time_days + β×dist_km + lat_penalty  
  (or time-only heavy in emergency).

---

## 13. Code examples

### Run a full simulation (CLI)

```bash
python main.py --start-lat 35 --start-lon -70 --target-lat 40 --target-lon -65 --out-plot route.png
```

### Run simulation from Python

```python
from datetime import datetime
from data_loader import open_cached
from simulator import simulate_route

provider = open_cached()
traj, times, days, energy, pct, mode, sail_frac = simulate_route(
    35, -70, 40, -65, 14, provider, start_time=datetime.utcnow(),
    sail_motor_ok=True, propeller_motor_ok=True, turning_motors_working=2,
)
print(f"Arrived in {days:.2f} days, saved {pct:.1f}% energy")
```

### Single step (vessel_model)

```python
from vessel_model import step

lat, lon = 35.0, -70.0
u, v = 0.1, 0.05
new_lat, new_lon, dx_s, dy_s, E, dx_sail, dy_sail = step(
    lat, lon, u, v, steering_angle_deg=0,
    sail_motor_ok=True, propeller_motor_ok=True, turning_motors_working=2,
)
print(f"New: ({new_lat}, {new_lon}), energy: {E}")
```

### Ask router for best angle

```python
from router import choose_steering
from datetime import datetime

def get_cur(lat, lon, t):
    return (0.1, 0.0, False)

angle, cost = choose_steering(
    35, -70, 40, -65, datetime.utcnow(), get_cur,
)
print(f"Steer at {angle}° (cost {cost})")
```

### Get currents from provider

```python
from data_loader import open_cached
from datetime import datetime

p = open_cached()
u, v, expired = p.get_currents(35, -70, datetime(2025, 2, 1))
print(f"u={u}, v={v}, expired={expired}")
```

---

That’s the full breakdown: what each file does, how it works, the math, and simple explanations plus code you can copy and adapt.
