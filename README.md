# Blue Vector

Ocean-current–aware routing for low-energy maritime transport: an algorithm that minimizes propulsion energy by riding ocean currents instead of fighting them. The motor is used **only to steer**—to hop into the right current (and wind) that carries the vessel toward the target.

## What it does

- **Steer into the right current**: Propulsion is for steering only; the algorithm chooses which direction to steer so the boat enters currents (and wind) that take it toward the target, like lane hopping.
- **Real operational data**: Uses ocean surface current fields (u, v) from NOAA RTOFS or a synthetic dataset when offline.
- **Time-varying vector field**: Routes in a dynamic flow; steering is optimized at each 6-hour step.
- **Quantified tradeoff**: Cost function combines propulsion energy, time to target, and distance; output includes % energy saved vs straight-line propulsion.
- **Wind and sail**: Parametric wind (westerlies / trade winds by latitude and season); optional sail displacement; **adaptive operation**: if the motor fails the system uses wind (sail-only); if wind is out it uses motor (motor-only).

## Install

```bash
cd Blue_Vector
pip install -r requirements.txt
```

Python 3.10+ recommended.

## Usage

### 1. Download current data (once)

```bash
python main.py --download-only
```

Optional: add `--bbox`, `--start-time`, `--forecast-days` (see Options below).

If OPeNDAP is unavailable, a small synthetic current field is created so you can run the demo offline.

### 2. Run simulation (offline)

```bash
python main.py
```

To save the map: `python main.py --out-plot route.png`  
Sail-only (motor failed): `python main.py --motor-failed`  
Motor-only (no wind): `python main.py --wind-out`

Defaults use a North Atlantic bounding box and a short route. Results are printed (arrival time, energy saved, scenario) and a plot is shown (or saved with `--out-plot`).

### Options

| Option | Description |
|--------|-------------|
| `--download-only` | Only fetch/cache NetCDF; do not run simulation |
| `--bbox` | Lat/lon bounding box: LAT_MIN LON_MIN LAT_MAX LON_MAX |
| `--start-time` | Forecast start date (YYYY-MM-DD) |
| `--forecast-days` | Forecast length in days (default: 7) |
| `--start-lat`, `--start-lon` | Vessel start position |
| `--target-lat`, `--target-lon` | Target position |
| `--max-days` | Maximum simulation time (days) |
| `--out-plot` | Save map to this path |
| `--data-dir` | Directory for cached NetCDF (default: `~/.blue_vector_data`) |
| `--motor-failed` | Sail-only mode (no motor) |
| `--wind-out` | Motor-only mode (no wind/sail) |

## Web app (animation with mocked data)

A React app runs the **same routing algorithm** with mocked current data so you can compare scenarios (favorable vs unfavorable current) and watch the route animate.

1. Start the API: `uvicorn server:app --reload --port 8000`
2. From `webapp/`: `npm install && npm run dev`
3. Open http://localhost:5173 — set start/target, pick scenario and mode, run simulation, then **Animate route** to see the vessel dot follow the computed path.

See `webapp/README.md` for details.

## Project layout

- `config.py` — Defaults (bbox, timestep, router weights, etc.)
- `data_loader.py` — Fetch/cache NetCDF; `get_currents(lat, lon, time)`; forecast-expiry handling
- `vessel_model.py` — Position update; steering bound; energy per step
- `router.py` — Receding-horizon: sample steering angles, simulate forward, minimize cost
- `simulator.py` — `simulate_route(...)`; returns trajectory, time, energy, % saved
- `main.py` — CLI and visualization entrypoint
- `viz.py` — Plot currents, optimized route, straight-line route
- `wind_model.py` — Parametric wind by latitude and season
- `mock_data.py` — Mock current providers for demos and API
- `server.py` — FastAPI server for the web app (`POST /simulate`)
- `webapp/` — React app: map, controls, dot animation
- `build.md` — Full specification

## Offline mode

After the first `--download-only` run, all routing uses the cached NetCDF. No network is used during `simulate_route`. If the simulation goes past the forecast end time, the last known current field is reused and steering range is reduced (see `config.FORECAST_EXPIRED_ANGLE_RANGE_DEG`).

## License

See repository.
