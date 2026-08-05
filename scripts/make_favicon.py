"""Generează favicon-ul aplicației: pin de locație alb pe fundal roșu (brand), rotunjit.
Desenat la 4× și scalat cu LANCZOS pentru margini fine; salvat multi-size .ico + PNG.
Rulează: python scripts/make_favicon.py
"""
from __future__ import annotations
from pathlib import Path
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
PUB = ROOT / "app/public"
RED = (214, 69, 43, 255)
WHITE = (255, 255, 255, 255)

S = 256
F = 4  # supersampling
n = S * F
img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
d = ImageDraw.Draw(img)

# fundal roșu, colțuri rotunjite
d.rounded_rectangle([0, 0, n - 1, n - 1], radius=int(0.22 * n), fill=RED)

# pin de locație (picătură): cerc + triunghi spre vârf, apoi gaura
cx, cy, r = 0.50 * n, 0.42 * n, 0.225 * n
d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=WHITE)
# triunghiul care coboară în vârf; laturile de sus ating cercul
d.polygon([(cx - r * 0.80, cy + r * 0.55), (cx + r * 0.80, cy + r * 0.55),
           (cx, 0.86 * n)], fill=WHITE)
# gaura (roșie) din centrul capului
h = 0.093 * n
d.ellipse([cx - h, cy - h, cx + h, cy + h], fill=RED)

icon = img.resize((S, S), Image.LANCZOS)
sizes = [16, 24, 32, 48, 64, 128, 256]
icon.save(PUB / "favicon.ico", sizes=[(s, s) for s in sizes])
icon.save(PUB / "favicon-32.png")
icon.resize((180, 180), Image.LANCZOS).save(PUB / "apple-touch-icon.png")
# iconițe PWA (manifest)
img.resize((192, 192), Image.LANCZOS).save(PUB / "icon-192.png")
img.resize((512, 512), Image.LANCZOS).save(PUB / "icon-512.png")
print(f"scris favicon.ico ({', '.join(map(str, sizes))}) + favicon-32 + apple-touch + icon-192/512")
