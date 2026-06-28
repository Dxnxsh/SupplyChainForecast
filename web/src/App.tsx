import { Routes, Route } from "react-router-dom";
import TopBar from "./components/TopBar";
import Dashboard from "./pages/Dashboard";
import Placeholder from "./pages/Placeholder";

export default function App() {
  return (
    <div className="wrap" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <TopBar />
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route
          path="/map"
          element={
            <Placeholder
              title="Global situation map"
              blurb="World map with the five sectors as geographic markers coloured by status, live disruption events plotted from geocoded news, and the Hormuz→Red Sea→Suez lane highlighting when shipping is disrupted. Next on the build list."
            />
          }
        />
        <Route
          path="/products"
          element={
            <Placeholder
              title="Product supply chain"
              blurb="iPhone / AirPods / EV / laptop exposure, composed from the sector predictions via an approximate bill of materials. Aggregates the working forecasts — it does not predict products directly."
            />
          }
        />
        <Route
          path="/accuracy"
          element={
            <Placeholder
              title="Model accuracy"
              blurb="Relevance precision/recall vs baselines, predictor walk-forward AUC, leakage-test badges, and the discovered topics — the technical evidence, read from the metric files."
            />
          }
        />
      </Routes>
    </div>
  );
}
