import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { AppSidebar } from "@/components/layout/AppSidebar";
import WorldMapDashboard from "./pages/WorldMapDashboard";
import SuppliersPage from "./pages/SuppliersPage";
import ResilienceHistoryPage from "./pages/ResilienceHistoryPage";
import NewsEventsPage from "./pages/NewsEventsPage";
import AdminPage from "./pages/AdminPage";
import NotFound from "./pages/NotFound";

const queryClient = new QueryClient();

const App = () => (
  <QueryClientProvider client={queryClient}>
    <TooltipProvider>
      <Toaster />
      <Sonner />
      <BrowserRouter>
        <div className="flex min-h-screen w-full bg-background">
          <AppSidebar />
          <Routes>
            <Route path="/" element={<WorldMapDashboard />} />
            <Route path="/suppliers" element={<SuppliersPage />} />
            <Route path="/forecast" element={<ResilienceHistoryPage />} />
            <Route path="/history" element={<ResilienceHistoryPage />} />
            <Route path="/news" element={<NewsEventsPage />} />
            <Route path="/admin" element={<AdminPage />} />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </div>
      </BrowserRouter>
    </TooltipProvider>
  </QueryClientProvider>
);

export default App;
