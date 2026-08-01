import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  // sub-cale la deploy (ex. „/unde-locuiesc-romanii/"); implicit „/" pentru dev
  base: process.env.VITE_BASE ?? "/",
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    strictPort: true,
    watch: { usePolling: true }, // bind mount în Docker pe macOS
  },
  optimizeDeps: {
    exclude: ["@duckdb/duckdb-wasm"],
  },
});
