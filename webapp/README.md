# Blue Vector Web App

React app that runs the Blue Vector routing algorithm with **mocked current data** and animates the vessel along the computed route.

## Run

1. **Start the API** (from project root):
   ```bash
   cd .. && uvicorn server:app --reload --host 0.0.0.0 --port 8000
   ```

2. **Start the app**:
   ```bash
   npm install
   npm run dev
   ```

3. Open http://localhost:5173. Set start/target, pick a **Current scenario** (favorable / unfavorable / cross / calm), pick **Mode** (combined / motor only / sail only), click **Run simulation**, then **Animate route** to watch the dot follow the algorithm’s path.

The algorithm is the real Blue Vector router; only the current field is mocked so you can compare “this current is better” vs “unfavorable” and see the route change.
