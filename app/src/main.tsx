import React from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import "./styles.css";
import "maplibre-gl/dist/maplibre-gl.css";

const DATA_URL = (import.meta.env.VITE_DATA_URL as string | undefined) ?? "http://localhost:8090";

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App dataUrl={DATA_URL} />
  </React.StrictMode>
);
