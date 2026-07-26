import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

declare const process: { env: Record<string, string | undefined> };

// Relative base so the built app can be served from any path (e.g. behind FastAPI later).
export default defineConfig({
  base: "./",
  plugins: [react()],
  server: { port: Number(process.env.PORT) || 5174 },
});
