Project Description – Algorithm Component

This project develops an ocean-current–aware routing algorithm for low-energy maritime transport. The broader system explores how autonomous cargo vessels can leverage large-scale ocean circulation to reduce propulsion energy by riding natural currents instead of continuously fighting them.

The focus of this component is the routing intelligence.

We are building an algorithm that:

• Ingests real operational ocean surface current data (u and v velocity fields) from scientific models such as NOAA RTOFS or Copernicus Marine.
• Represents the ocean as a time-varying vector field.
• Simulates vessel motion as the sum of environmental current drift and limited steering propulsion.
• Continuously optimizes steering direction to minimize propulsion energy while respecting arrival time constraints.
• Operates fully offline once forecast data is downloaded, enabling mid-ocean autonomy.

Mathematically, vessel motion is modeled as:

position(t+1) = position(t) + current_vector + steering_vector

Where:

current_vector is obtained from real ocean circulation datasets.

steering_vector is bounded by the vessel’s maximum propulsion capability.

The algorithm uses receding-horizon optimization:
At each timestep, it evaluates multiple candidate steering directions, simulates forward motion through the dynamic current field, computes a cost function (energy + time + distance penalties), and selects the direction minimizing total cost.

The objective is not shortest path, but minimum energy path in a time-dependent flow field.

This transforms ocean circulation from a constraint into a navigational asset.

The output of the algorithm includes:

Optimized trajectory

Estimated arrival time

Total propulsion energy used

Comparative energy savings versus straight-line propulsion

This module serves as the computational core of the system, demonstrating that intelligent routing in planetary-scale fluid dynamics can significantly reduce energy expenditure in long-distance maritime transport.

If you want a shorter, punchier version for a slide:

We are building an energy-minimizing routing algorithm that navigates autonomous vessels through real-time ocean current vector fields. Instead of fighting the ocean, the algorithm continuously adapts steering decisions to exploit prevailing flows, solving a minimum-energy path problem in a dynamic fluid environment.

You are building a Python-based ocean current routing simulation engine for a hackathon project.

Goal:
Create a working prototype that:

Downloads real ocean surface current data (u and v velocity components) from NOAA RTOFS or Copernicus Marine.

Stores the dataset locally (NetCDF).

Simulates an autonomous cargo vessel moving from point A to point B using ocean currents.

Minimizes propulsion energy while meeting a time constraint.

Works in offline mode after data is downloaded.

Technical Requirements:

Data Layer:

Use Python.

Use xarray to read NetCDF files.

Allow user to specify:

latitude/longitude bounding box

start time

forecast duration (e.g. 7–14 days)

Extract surface current components:

u (eastward velocity, m/s)

v (northward velocity, m/s)

Store dataset locally for offline simulation.

Vessel Model:

Vessel has:

max steering speed (e.g. 0.3 m/s)

no forward propulsion beyond steering vector

At each timestep:
position(t+1) = position(t) + current_vector + steering_vector

Use 6-hour time steps.

Convert lat/lon movement correctly using Earth radius (Haversine or spherical approximation).

Routing Algorithm:

Implement receding horizon optimization:
At each step:

Sample multiple steering directions (e.g. -45° to +45° relative to target bearing).

Simulate N steps forward (e.g. 5 days).

Compute cost function:

cost = propulsion_energy
+ alpha * time_to_target
+ beta * distance_to_target

Choose steering direction minimizing cost.

Repeat until vessel reaches target (within tolerance km).

Energy Model:

Propulsion energy ∝ magnitude of steering_vector² * time

Track cumulative propulsion energy.

Also compute:

hypothetical straight-line propulsion route energy

percentage energy savings

Offline Mode:

After dataset is downloaded:

System must run without internet.

All routing uses locally stored dataset.

If forecast window expires:

Continue drifting using last known current field.

Reduce steering aggressiveness.

Log forecast-expired warning.

Simulation Interface:
Create function:

simulate_route(
start_lat,
start_lon,
target_lat,
target_lon,
max_days,
)

Return:

trajectory (list of lat/lon)

total_time_days

total_propulsion_energy

percent_energy_saved

Visualization:

Plot:

vector field of currents

optimized route

straight-line route

Use matplotlib or plotly.

Print:

arrival time

energy saved

scenario label (e.g., favorable current vs unfavorable)

Architecture:
Organize into modules:

data_loader.py
vessel_model.py
router.py
simulator.py
main.py

This is a hackathon prototype. Prioritize clarity and modularity over production-level error handling.

Now let’s think like judges for 30 seconds.

What makes this impressive is not just “it runs.”

It’s that:

You are using real operational ocean circulation data.

You are solving optimal control in a time-varying vector field.

You are quantifying tradeoffs between time and energy.

That’s not random code. That’s applied physics.

If you want, next we can refine:
• The cost function mathematically
• The exact energy model
• Or how to simulate “good current season vs bad current season” cleanly

And we’ll sharpen it until it feels inevitable rather than experimental.