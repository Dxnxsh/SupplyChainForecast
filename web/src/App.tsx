import { Routes, Route } from "react-router-dom";
import TopBar from "./components/TopBar";
import MapView from "./pages/MapView";
import Dashboard from "./pages/Dashboard";
import Accuracy from "./pages/Accuracy";
import Placeholder from "./pages/Placeholder";

export default function App() {
  return (
    <div className="wrap" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <TopBar />
      <Routes>
        <Route path="/" element={<MapView />} />
        <Route path="/sectors" element={<Dashboard />} />
        <Route
          path="/products"
          element={
            <Placeholder
              title="Product supply chain"
              blurb="iPhone / AirPods / EV / laptop exposure, composed from the sector predictions via an approximate bill of materials. Aggregates the working forecasts — it does not predict products directly."
            />
          }
        />
        <Route path="/accuracy" element={<Accuracy />} />
      </Routes>
    </div>
  );
}
