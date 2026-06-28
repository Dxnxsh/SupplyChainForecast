import { Routes, Route } from "react-router-dom";
import TopBar from "./components/TopBar";
import MapView from "./pages/MapView";
import Dashboard from "./pages/Dashboard";
import Accuracy from "./pages/Accuracy";
import Products from "./pages/Products";

export default function App() {
  return (
    <div className="wrap" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <TopBar />
      <Routes>
        <Route path="/" element={<MapView />} />
        <Route path="/sectors" element={<Dashboard />} />
        <Route path="/products" element={<Products />} />
        <Route path="/accuracy" element={<Accuracy />} />
      </Routes>
    </div>
  );
}
