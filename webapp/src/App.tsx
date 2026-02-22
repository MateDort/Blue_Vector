import { useState, useCallback, useRef, useEffect } from "react";
import "./App.css";

const API_BASE = "http://localhost:8000";

/** Fixed route: China (Shanghai) → LA. 60-day trip simulated with real ocean current data. */
const CHINA_LA = {
  start: { lat: 31.2, lon: 121.5 },
  target: { lat: 33.75, lon: -118.25 },
};
const MAX_DAYS = 60;
/** 60-day voyage compressed into 1 minute */
const ANIMATION_DURATION_MS = 60 * 1000;

type Point = { lat: number; lon: number };

interface SimulateResponse {
  trajectory: Point[];
  times: string[];
  total_time_days: number;
  total_energy: number;
  percent_energy_saved: number;
  mode: string;
  sail_fraction: number;
}

function latLonToXY(
  lat: number,
  lon: number,
  bounds: { latMin: number; latMax: number; lonMin: number; lonMax: number },
  width: number,
  height: number
): [number, number] {
  const x = ((lon - bounds.lonMin) / (bounds.lonMax - bounds.lonMin)) * width;
  const y = (1 - (lat - bounds.latMin) / (bounds.latMax - bounds.latMin)) * height;
  return [x, y];
}

function getBounds(trajectory: Point[], start: Point, target: Point, padding = 0.1) {
  const lats = [...trajectory.map((p) => p.lat), start.lat, target.lat];
  const lons = [...trajectory.map((p) => p.lon), start.lon, target.lon];
  const latMin = Math.min(...lats);
  const latMax = Math.max(...lats);
  const lonMin = Math.min(...lons);
  const lonMax = Math.max(...lons);
  const dLat = (latMax - latMin) * padding || 1;
  const dLon = (lonMax - lonMin) * padding || 1;
  return {
    latMin: latMin - dLat,
    latMax: latMax + dLat,
    lonMin: lonMin - dLon,
    lonMax: lonMax + dLon,
  };
}

export default function App() {
  const start = CHINA_LA.start;
  const target = CHINA_LA.target;
  const [trajectory, setTrajectory] = useState<Point[]>([]);
  const [times, setTimes] = useState<string[]>([]);
  const [stats, setStats] = useState<SimulateResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadPhase, setLoadPhase] = useState<"idle" | "downloading" | "simulating">("idle");
  const [error, setError] = useState<string | null>(null);
  const [animating, setAnimating] = useState(false);
  const [motorFailed, setMotorFailed] = useState(false);
  const [animProgress, setAnimProgress] = useState(0);
  const animStartRef = useRef<number>(0);
  const rafRef = useRef<number | null>(null);
  const vesselCircleRef = useRef<SVGCircleElement | null>(null);
  const animDataRef = useRef<{
    trajectory: Point[];
    bounds: ReturnType<typeof getBounds>;
    width: number;
    height: number;
  } | null>(null);

  const runSimulation = useCallback(async (withBrokenMotor = false) => {
    setLoading(true);
    setError(null);
    setTrajectory([]);
    setStats(null);
    setMotorFailed(withBrokenMotor);
    setAnimProgress(0);
    setLoadPhase("downloading");
    try {
      await fetch(`${API_BASE}/ensure_data`);
      setLoadPhase("simulating");
      const res = await fetch(`${API_BASE}/simulate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          start_lat: start.lat,
          start_lon: start.lon,
          target_lat: target.lat,
          target_lon: target.lon,
          max_days: MAX_DAYS,
          use_real_data: true,
          mode: withBrokenMotor ? "sail_only" : "combined",
          scenario: "favorable",
          propeller_motor_failed: withBrokenMotor,
        }),
      });
      if (!res.ok) throw new Error(await res.text());
      const data: SimulateResponse = await res.json();
      setTrajectory(data.trajectory);
      setTimes(data.times);
      setStats(data);
      setAnimating(true);
      animStartRef.current = performance.now();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Request failed");
    } finally {
      setLoading(false);
      setLoadPhase("idle");
    }
  }, []);

  const triggerMotorFailure = useCallback(async () => {
    if (trajectory.length <= 1 || times.length <= 1 || motorFailed) return;
    let safeIdx: number;
    if (animating) {
      const elapsed = performance.now() - animStartRef.current;
      const progress = Math.min(1, elapsed / ANIMATION_DURATION_MS);
      safeIdx = Math.min(
        trajectory.length - 1,
        Math.max(0, Math.floor(progress * (trajectory.length - 1)))
      );
    } else {
      const lo = Math.floor(trajectory.length * 0.1);
      const hi = Math.floor(trajectory.length * 0.9);
      safeIdx = Math.min(trajectory.length - 1, lo + Math.floor(Math.random() * (hi - lo + 1)));
    }
    const from = trajectory[safeIdx];
    const startTimeIso = times[safeIdx];
    setMotorFailed(true);
    setLoadPhase("simulating");
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/simulate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          start_lat: start.lat,
          start_lon: start.lon,
          target_lat: target.lat,
          target_lon: target.lon,
          max_days: MAX_DAYS,
          use_real_data: true,
          motor_failed: true,
          from_lat: from.lat,
          from_lon: from.lon,
          start_time_iso: startTimeIso,
        }),
      });
      if (!res.ok) throw new Error(await res.text());
      const data: SimulateResponse = await res.json();
      const head = trajectory.slice(0, safeIdx + 1);
      const tail = data.trajectory.slice(1);
      const newTimes = [...times.slice(0, safeIdx + 1), ...data.times.slice(1)];
      setTrajectory([...head, ...tail]);
      setTimes(newTimes);
      setStats(data);
      setAnimProgress(0);
      animStartRef.current = performance.now();
      setAnimating(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Request failed");
      setMotorFailed(false);
    } finally {
      setLoading(false);
      setLoadPhase("idle");
    }
  }, [trajectory, times, motorFailed, animating]);

  // Animation: update vessel circle position directly in rAF so it moves every frame
  useEffect(() => {
    if (!animating || trajectory.length <= 1) return;
    animStartRef.current = performance.now();
    animDataRef.current = {
      trajectory,
      bounds: getBounds(trajectory, start, target),
      width: 700,
      height: 400,
    };
    let cancelled = false;
    const tick = () => {
      if (cancelled) return;
      const data = animDataRef.current;
      if (!data) return;
      const elapsed = performance.now() - animStartRef.current;
      const p = Math.min(1, elapsed / ANIMATION_DURATION_MS);
      setAnimProgress(p);
      if (p >= 1) {
        setAnimating(false);
        return;
      }
      const idx = Math.min(
        data.trajectory.length - 1,
        Math.floor(p * (data.trajectory.length - 1))
      );
      const pt = data.trajectory[idx];
      const [x, y] = latLonToXY(pt.lat, pt.lon, data.bounds, data.width, data.height);
      const circle = vesselCircleRef.current;
      if (circle) {
        circle.setAttribute("cx", String(x));
        circle.setAttribute("cy", String(y));
      }
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => {
      cancelled = true;
      if (rafRef.current != null) {
        cancelAnimationFrame(rafRef.current);
        rafRef.current = null;
      }
    };
  }, [animating, trajectory, start, target]);

  const animIndex =
    trajectory.length > 1
      ? animating
        ? Math.min(trajectory.length - 1, Math.floor(animProgress * (trajectory.length - 1)))
        : trajectory.length - 1
      : 0;

  const replayAnimation = () => {
    setAnimProgress(0);
    setAnimating(true);
  };

  const bounds =
    trajectory.length > 0
      ? getBounds(trajectory, start, target)
      : getBounds([], start, target, 0.2);
  const width = 700;
  const height = 400;

  const [startX, startY] = latLonToXY(start.lat, start.lon, bounds, width, height);
  const [targetX, targetY] = latLonToXY(target.lat, target.lon, bounds, width, height);
  const pathD =
    trajectory.length > 1
      ? trajectory
          .map((p, i) => {
            const [x, y] = latLonToXY(p.lat, p.lon, bounds, width, height);
            return `${i === 0 ? "M" : "L"} ${x} ${y}`;
          })
          .join(" ")
      : "";
  const currentPoint = trajectory[animIndex] ?? start;
  const [dotX, dotY] = latLonToXY(currentPoint.lat, currentPoint.lon, bounds, width, height);

  return (
    <div className="app">
      <header>
        <h1>Blue Vector</h1>
        <p>China → LA: 60-day voyage with real ocean currents, in a 1-minute animation</p>
      </header>

      <section className="section">
        <h2>Route</h2>
        <p className="route-desc">Shanghai (31.2°N, 121.5°E) → Los Angeles (33.75°N, 118.25°W). Real current and wind data loaded on run.</p>
        <p className="motors-desc">Vessel has 4 motors: 1 sail, 1 propeller, 2 turning. Press <strong>Break motor</strong> anytime to throw an obstacle: the motor fails at a random point (or at the current position if the animation is playing), and the algorithm adapts by recalculating the rest of the route under sail only.</p>
      </section>

      <div className="run-row">
        <button
          type="button"
          className="run-btn"
          onClick={() => runSimulation(false)}
          disabled={loading}
        >
          {loading
            ? loadPhase === "downloading"
              ? "Downloading current data…"
              : "Running 60-day simulation…"
            : "Run 60-day simulation"}
        </button>
        <button
          type="button"
          className="break-motor-start-btn"
          onClick={() => runSimulation(true)}
          disabled={loading}
          title="Run the voyage with the motor already broken (sail-only from start)"
        >
          Start with broken motor
        </button>
        {trajectory.length > 1 && !loading && (
          <button type="button" className="replay-btn" onClick={replayAnimation} disabled={animating}>
            {animating ? "Playing (1 min)…" : "Replay"}
          </button>
        )}
        {trajectory.length > 1 && !motorFailed && (
          <button
            type="button"
            className="motor-broke-btn"
            onClick={triggerMotorFailure}
            disabled={loading}
            title="Throw obstacle: break motor at a random point (or current position if playing). The algorithm adapts and recalculates the rest of the route under sail only."
          >
            Break motor
          </button>
        )}
      </div>

      {error && <div className="error">{error}</div>}

      <div className="map-container">
        <svg viewBox={`0 0 ${width} ${height}`} className="map">
          <rect width={width} height={height} fill="#e8f4f8" />
          {[0.25, 0.5, 0.75].map((t) => (
            <line key={`v${t}`} x1={width * t} y1={0} x2={width * t} y2={height} stroke="#ccc" strokeWidth={0.5} />
          ))}
          {[0.25, 0.5, 0.75].map((t) => (
            <line key={`h${t}`} x1={0} y1={height * t} x2={width} y2={height * t} stroke="#ccc" strokeWidth={0.5} />
          ))}
          <line x1={startX} y1={startY} x2={targetX} y2={targetY} stroke="#999" strokeWidth={1} strokeDasharray="4 2" />
          {pathD && <path d={pathD} fill="none" stroke="#1a5fb4" strokeWidth={2} />}
          <circle cx={startX} cy={startY} r={8} fill="#2e7d32" />
          <text x={startX} y={startY - 12} textAnchor="middle" fontSize={10}>China</text>
          <circle cx={targetX} cy={targetY} r={8} fill="#c62828" />
          <text x={targetX} y={targetY - 12} textAnchor="middle" fontSize={10}>LA</text>
          <circle
            ref={vesselCircleRef}
            cx={dotX}
            cy={dotY}
            r={6}
            fill="#1565c0"
            className="vessel-dot"
          />
        </svg>
        <div className="map-caption">
          China → LA · 60 days → 1 min · Lat {bounds.latMin.toFixed(1)} – {bounds.latMax.toFixed(1)} | Lon {bounds.lonMin.toFixed(1)} – {bounds.lonMax.toFixed(1)}
        </div>
        {trajectory.length > 1 && (
          <div className="anim-progress-bar">
            <div
              className="anim-progress-fill"
              style={{ width: `${animProgress * 100}%` }}
            />
          </div>
        )}
      </div>

      {stats && (
        <div className="stats">
          <h3>Results</h3>
          <p>Mode: <strong>{stats.mode}</strong></p>
          <p>Time: <strong>{stats.total_time_days.toFixed(2)}</strong> days</p>
          <p>Energy saved: <strong>{stats.percent_energy_saved.toFixed(1)}%</strong> vs straight-line</p>
          {stats.sail_fraction > 0 && (
            <p>Sail: <strong>{(stats.sail_fraction * 100).toFixed(1)}%</strong> of displacement</p>
          )}
        </div>
      )}
    </div>
  );
}
