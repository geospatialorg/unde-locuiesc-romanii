#!/bin/bash
# Entrypoint pentru serviciul climate-cron: programează descărcarea zilnică a datelor
# climatice la CRON_HOUR:CRON_MIN (implicit 10:00, fusul din TZ). Variabilele de mediu
# necesare jobului le scriem direct în fișierul cron.d (cron le aplică nativ joburilor),
# citindu-le prin expansiune de shell (robustă, spre deosebire de `printenv` sub docker exec).
set -e

CRON_HOUR="${CRON_HOUR:-10}"
CRON_MIN="${CRON_MIN:-0}"

{
  echo "SHELL=/bin/bash"
  for k in PATH PYTHONPATH TZ ULR_DATA_IN ULR_DATA_OUT ULR_STAGING ULR_CLIMATE_YEAR; do
    eval "v=\${$k:-}"
    [ -n "$v" ] && echo "$k=$v"
  done
  echo "${CRON_MIN} ${CRON_HOUR} * * * root cd /app && python -m ulr_pipeline.climate_refresh once > /proc/1/fd/1 2> /proc/1/fd/2"
} > /etc/cron.d/climate
chmod 0644 /etc/cron.d/climate

echo "[climate-cron] pornit — actualizare zilnică la ${CRON_HOUR}:$(printf '%02d' "${CRON_MIN}") (${TZ:-UTC}); sursă: opendata.meteoromania.ro"

# opțional: o rulare la pornire (util pentru prima punere în funcțiune / testare)
if [ "${RUN_ON_START:-0}" = "1" ]; then
  echo "[climate-cron] rulez o actualizare la pornire (RUN_ON_START=1)…"
  ( cd /app && python -m ulr_pipeline.climate_refresh once ) || true
fi

exec cron -f
