"""Actualizarea zilnică a datelor climatice.

Descarcă grilele zilnice NetCDF de la opendata.meteoromania.ro pentru anul curent
(URL-ul se adaptează singur la an — vezi config.CLIMATE_URLS), le validează, le
înlocuiește atomic în data/, apoi re-rulează agregarea climatică și re-asamblează
produsele publicate (climate.parquet, seriile climatice județene, registry.json).

  python -m ulr_pipeline.climate_refresh once    # o singură actualizare (chemată de cron)

Programarea zilnică (ora 10:00) o face serviciul `climate-cron` din docker-compose.
Presupune că pipeline-ul complet a rulat deja o dată (există data/staging).
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import time
import urllib.request
from datetime import datetime, timezone

import xarray as xr

from .config import CLIMATE_URLS, CLIMATE_YEAR, SRC, STAGING, ensure_dirs

UA = "unde-locuiesc-romanii/0.1 (actualizare date climatice deschise)"


def _log(msg: str) -> None:
    print(f"[climate {datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S}Z] {msg}", flush=True)


def _download(url: str, dest, var: str) -> bool:
    """Descarcă într-un fișier temporar, validează NetCDF-ul, apoi înlocuiește atomic.
    Întoarce True dacă fișierul de destinație a fost actualizat."""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    tmp = tempfile.NamedTemporaryFile(delete=False, dir=str(dest.parent), suffix=".nc.part")
    tmp.close()
    try:
        with urllib.request.urlopen(req, timeout=120) as r, open(tmp.name, "wb") as f:
            shutil.copyfileobj(r, f)
        # validare: se deschide ca NetCDF și are variabila + o dimensiune de timp
        with xr.open_dataset(tmp.name) as ds:
            if var not in ds.variables:
                raise ValueError(f"variabila „{var}” lipsește din NetCDF")
            ndays = int(ds.sizes.get("time", 0))
        size_mb = round(dest.parent.joinpath(tmp.name).stat().st_size / 1e6, 1)
        shutil.move(tmp.name, dest)
        _log(f"  {dest.name}: {size_mb} MB, {ndays} zile ✓")
        return True
    except Exception as e:
        _log(f"  EȘEC {dest.name}: {e!r} — păstrez fișierul anterior")
        try:
            import os
            os.unlink(tmp.name)
        except OSError:
            pass
        return False


def refresh() -> None:
    ensure_dirs()
    if not (STAGING / "cells.parquet").exists():
        _log("EROARE: lipsește data/staging (rulează întâi pipeline-ul complet). Renunț.")
        return

    _log(f"actualizez datele climatice pentru anul {CLIMATE_YEAR}…")
    ok = 0
    for var_key, url in CLIMATE_URLS.items():
        nc_var = {"precip": "daily_precipitation", "tmin": "daily_minimum_temp",
                  "tmax": "daily_maximum_temp"}[var_key]
        if _download(url, SRC[var_key], nc_var):
            ok += 1

    if ok == 0:
        _log("niciun fișier descărcat — nu re-procesez.")
        return

    # re-agregare climatică + re-asamblarea produselor publicate
    from .steps.climate import step_climate
    from .export import step_export

    t0 = time.time()
    step_climate()
    step_export()
    _log(f"gata: produse actualizate în {time.time() - t0:.1f}s "
         f"({ok}/{len(CLIMATE_URLS)} fișiere reîmprospătate)")


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "once"
    if mode != "once":
        sys.exit("folosire: python -m ulr_pipeline.climate_refresh once")
    refresh()


if __name__ == "__main__":
    main()
