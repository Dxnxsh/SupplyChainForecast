import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AnimatePresence } from "framer-motion";
import { BrowserRouter, Routes, Route, useLocation } from "react-router-dom";
import { AppSidebar } from "@/components/layout/AppSidebar";
import { PageTransition } from "@/components/layout/PageTransition";
import WorldMapDashboard from "./pages/WorldMapDashboard";
import SuppliersPage from "./pages/SuppliersPage";
import ResilienceHistoryPage from "./pages/ResilienceHistoryPage";
import NewsEventsPage from "./pages/NewsEventsPage";
import AdminPage from "./pages/AdminPage";
import NotFound from "./pages/NotFound";

const queryClient = new QueryClient();

function AnimatedRoutes() {
  const location = useLocation();
  return (
    <AnimatePresence mode="wait" initial={false}>
      <Routes location={location} key={location.pathname}>
        <Route path="/" element={<PageTransition><WorldMapDashboard /></PageTransition>} />
        <Route path="/suppliers" element={<PageTransition><SuppliersPage /></PageTransition>} />
        <Route path="/forecast" element={<PageTransition><ResilienceHistoryPage /></PageTransition>} />
        <Route path="/history" element={<PageTransition><ResilienceHistoryPage /></PageTransition>} />
        <Route path="/news" element={<PageTransition><NewsEventsPage /></PageTransition>} />
        <Route path="/admin" element={<PageTransition><AdminPage /></PageTransition>} />
        <Route path="*" element={<PageTransition><NotFound /></PageTransition>} />
      </Routes>
    </AnimatePresence>
  );
}

const App = () => (
  <QueryClientProvider client={queryClient}>
    <TooltipProvider>
      <Toaster />
      <Sonner />
      <BrowserRouter>
        <div className="flex min-h-screen w-full bg-background">
          <AppSidebar />
          <AnimatedRoutes />
        </div>
      </BrowserRouter>
    </TooltipProvider>
  </QueryClientProvider>
);

export default App;
