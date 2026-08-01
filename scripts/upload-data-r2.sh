#!/usr/bin/env bash
# Urcă produsele publicate (data/out) în bucket-ul R2, cu rclone.
# Cere un remote rclone numit „r2" (vezi DEPLOY.md / pasul 5) SAU variabilele de mediu de mai jos.
#
#   R2_ACCOUNT_ID   – id-ul contului Cloudflare (din endpoint-ul S3)
#   R2_ACCESS_KEY   – Access Key ID din token-ul R2
#   R2_SECRET_KEY   – Secret Access Key din token-ul R2
#   R2_BUCKET       – numele bucket-ului (ex. unde-locuiesc-romanii)
#
# Utilizare:  ./scripts/upload-data-r2.sh
set -euo pipefail

SRC="${1:-data/out}"
BUCKET="${R2_BUCKET:?setează R2_BUCKET}"

# config rclone „la zbor" din env, dacă nu ai deja un remote [r2] configurat
if ! rclone listremotes 2>/dev/null | grep -q '^r2:'; then
  export RCLONE_CONFIG_R2_TYPE=s3
  export RCLONE_CONFIG_R2_PROVIDER=Cloudflare
  export RCLONE_CONFIG_R2_ACCESS_KEY_ID="${R2_ACCESS_KEY:?setează R2_ACCESS_KEY}"
  export RCLONE_CONFIG_R2_SECRET_ACCESS_KEY="${R2_SECRET_KEY:?setează R2_SECRET_KEY}"
  export RCLONE_CONFIG_R2_ENDPOINT="https://${R2_ACCOUNT_ID:?setează R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
  export RCLONE_CONFIG_R2_ACL=private
fi

echo "Sincronizez $SRC → r2:$BUCKET (climate.zarr are multe fișiere mici — merge în paralel)…"
rclone copy "$SRC" "r2:$BUCKET" \
  --transfers 32 --checkers 32 --fast-list --progress \
  --s3-no-check-bucket

echo "Gata. Verifică: curl -I -H 'Range: bytes=0-99' <URL_PUBLIC>/registry.json  (aștepți 206)"
