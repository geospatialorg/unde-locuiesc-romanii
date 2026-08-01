import proj4 from "proj4";

// EPSG:3035 — ETRS89-LAEA, spațiul canonic al grilei
proj4.defs(
  "EPSG:3035",
  "+proj=laea +lat_0=52 +lon_0=10 +x_0=4321000 +y_0=3210000 +ellps=GRS80 +towgs84=0,0,0,0,0,0,0 +units=m +no_defs"
);

const to3035 = proj4("EPSG:4326", "EPSG:3035");

/** (lon, lat) → (E, N) în EPSG:3035 */
export function lonLatTo3035(lon: number, lat: number): [number, number] {
  return to3035.forward([lon, lat]) as [number, number];
}

/** (E, N) în EPSG:3035 → (lon, lat) */
export function e3035ToLonLat(e: number, n: number): [number, number] {
  return to3035.inverse([e, n]) as [number, number];
}

const R = 6378137;
/** lon/lat → metri Web Mercator (sferic, ca în MapLibre) */
export function lonToMercX(lon: number): number {
  return (R * lon * Math.PI) / 180;
}
export function latToMercY(lat: number): number {
  return R * Math.log(Math.tan(Math.PI / 4 + (lat * Math.PI) / 360));
}
export function mercXToLon(x: number): number {
  return (x / R) * (180 / Math.PI);
}
export function mercYToLat(y: number): number {
  return (2 * Math.atan(Math.exp(y / R)) - Math.PI / 2) * (180 / Math.PI);
}
