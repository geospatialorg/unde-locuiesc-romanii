import React from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import "./styles.css";
import "maplibre-gl/dist/maplibre-gl.css";

// DuckDB-WASM (read_parquet) are nevoie de URL absolut http(s); o cale relativă
// „/…/data" ar fi interpretată ca fișier local în FS-ul virtual WASM → „No files found".
// Rezolvăm față de origin-ul curent: rămîne same-origin (prin Caddy), dar devine absolut.
const RAW_DATA_URL = (import.meta.env.VITE_DATA_URL as string | undefined) ?? "http://localhost:8090";
const DATA_URL = new URL(RAW_DATA_URL, window.location.href).href.replace(/\/$/, "");

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App dataUrl={DATA_URL} />
  </React.StrictMode>
);
