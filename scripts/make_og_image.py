"""Generează imaginea de social preview (Open Graph, 1200×630) a aplicației:
bandă de titlu pe brand + harta reală de densitate a populației (din core.parquet).
Rulează: python scripts/make_og_image.py  →  app/public/og-image.png
"""
from __future__ import annotations
from math import cos, radians
from pathlib import Path

import duckdb
import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# DejaVu Sans nu are ș/ț cu virgulă-jos; Arial le randează corect (font local, imaginea
# e pre-generată și versionată — nu depinde de CI)
matplotlib.rcParams["font.family"] = "sans-serif"
matplotlib.rcParams["font.sans-serif"] = ["Arial", "DejaVu Sans"]
from matplotlib.colors import LogNorm
from matplotlib.patches import FancyBboxPatch

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "data/out/core.parquet"
COUNTY = ROOT / "data/out/county.geojson"
OUT = ROOT / "app/public/og-image.png"

RED = "#d6452b"
INK = "#1d2530"
BG = "#fbfcfe"

# populația pe celule locuite
df = duckdb.connect().execute(
    f"SELECT lon, lat, pop_total FROM read_parquet('{CORE}') WHERE pop_total > 0"
).fetchdf()
counties = gpd.read_file(COUNTY).to_crs(4326)

W, H = 1200, 630
LEFT = 0.38  # lățimea panoului de titlu (roșu), restul e harta
fig = plt.figure(figsize=(W / 100, H / 100), dpi=100)
fig.patch.set_facecolor(BG)

# --- harta (dreapta, umple pe verticală) ---
ax = fig.add_axes([LEFT, 0, 1 - LEFT, 1])
ax.set_facecolor(BG)
ax.axis("off")
ax.set_aspect(1 / cos(radians(45.9)))
counties.boundary.plot(ax=ax, color="#c9d0da", linewidth=0.4, zorder=1)
df = df.sort_values("pop_total")  # cele dense deasupra
ax.scatter(
    df["lon"], df["lat"], c=df["pop_total"], cmap="Reds",
    norm=LogNorm(vmin=1, vmax=10000), s=2.2, linewidths=0, alpha=0.9, zorder=2,
)
ax.set_xlim(20.2, 29.8)
ax.set_ylim(43.5, 48.35)

# --- panoul de titlu (stânga, roșu) ---
panel = FancyBboxPatch(
    (0, 0), LEFT, 1, transform=fig.transFigure,
    boxstyle="square,pad=0", facecolor=RED, edgecolor="none", zorder=5,
)
fig.patches.append(panel)
fig.text(0.045, 0.70, "Unde locuiesc\nromânii?", color="white",
         fontsize=37, fontweight="bold", va="top", linespacing=1.08, zorder=6)
fig.text(0.045, 0.44, "Câți români locuiesc\nîntr-un loc și cum\narată viața acolo",
         color="#ffe0d6", fontsize=19, va="top", linespacing=1.35, zorder=6)
fig.text(0.045, 0.075, "unde.geo-spatial.org", color="white",
         fontsize=16, fontweight="bold", va="center", zorder=6)

fig.savefig(OUT, dpi=100, facecolor=BG)
print(f"scris {OUT} ({W}×{H})")
