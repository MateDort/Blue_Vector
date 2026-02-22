"""
Central defaults for Blue Vector ocean-current routing.
Tune bounding box, data source, and simulation parameters here or via CLI.
"""
import os
from datetime import datetime, timedelta

# Data
DATA_DIR = os.environ.get("BLUE_VECTOR_DATA", os.path.join(os.path.expanduser("~"), ".blue_vector_data"))
DEFAULT_BBOX = (25.0, -80.0, 45.0, -60.0)  # (lat_min, lon_min, lat_max, lon_max) North Atlantic
# North Pacific: China (Shanghai) to LA — lon 122°E to 242°E (or -118°W)
PACIFIC_BBOX_CHINA_LA = (25.0, 122.0, 45.0, 242.0)  # (lat_min, lon_min, lat_max, lon_max)
CHINA_LA_START = (31.2, 121.5)   # Shanghai area
CHINA_LA_TARGET = (33.75, -118.25)  # LA
DEFAULT_PACIFIC_FORECAST_DAYS = 7   # real data typically 7 days; sim runs 60 days reusing last field after
DEFAULT_PACIFIC_MAX_DAYS = 60
DEFAULT_START_TIME = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
DEFAULT_FORECAST_DAYS = 7

# Vessel: 4 motors — 1 sail, 1 propeller, 2 turning
TIMESTEP_HOURS = 6
MAX_STEERING_SPEED_MS = 0.3   # full steering when both turning motors ok
EARTH_RADIUS_M = 6_371_000
# Motor availability (set False or count for failure scenarios)
SAIL_MOTOR_AVAILABLE = True       # 1 motor: powers/controls sail
PROPELLER_MOTOR_AVAILABLE = True  # 1 motor: drives propeller (steering thrust)
TURNING_MOTORS_WORKING = 2        # 2 motors to turn: 2=full, 1=half steering rate, 0=no steering

# Router
HORIZON_DAYS = 5
ANGLE_RANGE_DEG = 45  # -45 to +45 relative to bearing to target
ANGLE_STEP_DEG = 5
ALPHA = 1.0   # weight for time_to_target in cost
BETA = 1.0    # weight for distance_to_target in cost
DISTANCE_TOLERANCE_KM = 20.0
# Current-awareness: propeller only for moving between currents (and emergency)
# Favorability < this = "bad" current → we should plan to change current
CURRENT_FAVORABILITY_BAD_THRESHOLD = 0.0
# Penalize using propeller when already in a good current (save prop for lane changes)
PROPELLER_SAVE_IN_GOOD_CURRENT_WEIGHT = 2.0  # energy *= (1 + this * max(0, favorability))
# Penalize being in bad current (encourage steering into better current)
BAD_CURRENT_PENALTY_WEIGHT = 1.0  # cost += this * max(0, -favorability) per step
# Emergency to shore: minimize time only (ignore energy)
EMERGENCY_TIME_ONLY_ALPHA = 10.0  # when emergency, cost = alpha*time + beta*dist (alpha high)

# Offline / forecast expiry
FORECAST_EXPIRED_ANGLE_RANGE_DEG = 20  # narrower when forecast expired

# Adaptive operation (derived from 4 motors for backward compatibility)
# MOTOR_AVAILABLE = propeller ok and at least 1 turning motor; WIND_AVAILABLE = sail motor ok
MOTOR_AVAILABLE = True
WIND_AVAILABLE = True
SAIL_EFFICIENCY = 0.35  # fraction of wind velocity contributing to displacement (when sail motor ok)

# Latitude penalty to avoid trade-wind trap (eastbound: stay north of this)
SOUTH_LAT_LIMIT_DEG = 28.0
LATITUDE_PENALTY_WEIGHT = 0.0  # set > 0 to penalize going too far south
