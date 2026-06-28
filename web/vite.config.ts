import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Relative base so the built app can be served from any path (e.g. behind FastAPI later).
export default defineConfig({
  base: "./",
  plugins: [react()],
  server: { port: 5174 },
});
