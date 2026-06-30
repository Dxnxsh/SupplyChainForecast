import { Routes, Route } from "react-router-dom";
import { DateProvider } from "./lib/DateContext";
import TopBar from "./components/TopBar";
import DateWheel from "./components/DateWheel";
import MapView from "./pages/MapView";
import Dashboard from "./pages/Dashboard";
import Accuracy from "./pages/Accuracy";
import Products from "./pages/Products";
import Feed from "./pages/Feed";

export default function App() {
  return (
    <DateProvider>
      <div className="wrap" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <TopBar />
        <DateWheel />
        <Routes>
          <Route path="/" element={<MapView />} />
          <Route path="/sectors" element={<Dashboard />} />
          <Route path="/products" element={<Products />} />
          <Route path="/accuracy" element={<Accuracy />} />
          <Route path="/feed" element={<Feed />} />
        </Routes>
      </div>
    </DateProvider>
  );
}
