import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The proxy is the reason the frontend can call "/api/jobs" with no host and
// no CORS headers in development: Vite forwards anything starting with /api
// to the Python server on 8000, so the browser only ever sees one origin.
//
// In production there is no Vite, so the built app reads VITE_API_BASE and
// calls the deployed API directly -- which is why api/main.py still sets CORS.
const proxy = {
  "/api": {
    target: "http://127.0.0.1:8000",
    changeOrigin: true,
  },
};

export default defineConfig({
  plugins: [react()],
  // Relative base so the build works at https://user.github.io/<repo>/
  // as well as at a domain root. Absolute paths would 404 on Pages.
  base: "./",
  server: { proxy },
  // "npm run preview" serves the production build locally, and needs the same
  // forwarding or the preview would have no API to talk to.
  preview: { proxy },
});
