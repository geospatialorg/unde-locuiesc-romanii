# Deploy — „Unde locuiesc românii?"

Arhitectura de producție: **totul pe un VM**, servit **same-origin** sub sub-calea
`https://services.geo-spatial.org/unde-locuiesc-romanii/`. Un singur Caddy (port intern
`8080`) servește frontend-ul + datele + face proxy la serviciul de rutare. TLS și cache-ul
le adaugă **Cloudflare** (sau reverse-proxy-ul gazdei) în față.

```
Internet → Cloudflare (TLS+cache) → nginx :80/:443 → 127.0.0.1:${APP_PORT} → Caddy (container :8080) ┬─ /unde-locuiesc-romanii/       → frontend (app/dist)
                                                                                                    ├─ /unde-locuiesc-romanii/data/* → fișiere (data/out)
                                                                                                    └─ /unde-locuiesc-romanii/api/*  → routing-api (pgRouting)
        servicii de fundal: warnings · forecast · climate-cron · routing-db
```

`APP_PORT` (implicit `28173`, în `.env`) e portul de host spre care duce nginx-ul — ales exotic
fiindcă `8080` e deja ocupat pe VM. Caddy rămâne pe `:8080` **intern** în container.

Frontend-ul cere `${VITE_DATA_URL}/registry.json`, parquet-uri etc. și `${VITE_ROUTING_URL}/route`.
În producție ambele sunt pe **același domeniu** (fără CORS):
- `VITE_DATA_URL=https://services.geo-spatial.org/unde-locuiesc-romanii/data`
- `VITE_ROUTING_URL=https://services.geo-spatial.org/unde-locuiesc-romanii/api`
- `VITE_BASE=/unde-locuiesc-romanii/` (setat automat în workflow-ul de deploy)

---

## 1. Punere în funcțiune pe VM (o singură dată)

1. **Docker + Docker Compose** instalate; deschide portul `8080` doar către proxy/Cloudflare.
2. **Clonează repo-ul** în directorul de deploy (ex. `~/unde-locuiesc-romanii`) — trebuie să fie
   aceeași cale ca secretul `DEPLOY_PATH`.
3. **`.env`** (copiat din `.env.example`): setează `ROUTING_DB_PASSWORD` și, dacă folosești CAMS,
   `ADS_API_KEY`.
4. **Adu datele pe VM.** `data/` NU e în git (21 GB). Două opțiuni:
   - rulează pipeline-ul pe VM (are nevoie de fișierele-sursă din `data/` + spațiu):
     `docker compose run --rm pipeline python -m ulr_pipeline.run all`
   - sau copiază de pe mașina locală doar produsele: `rsync -az data/out/ vm:~/unde-locuiesc-romanii/data/out/`
     (plus fișierele-sursă necesare pollerelor/refresh-ului climatic).
5. **Graful de rutare** (o singură dată):
   ```bash
   docker compose -f docker-compose.prod.yml up -d routing-db
   docker compose -f docker-compose.prod.yml --profile routing-import run --rm routing-import
   ```
6. **Pornește tot:**
   ```bash
   docker compose -f docker-compose.prod.yml up -d --build
   ```
7. Test local pe VM: `curl -I http://127.0.0.1:8080/unde-locuiesc-romanii/data/registry.json` → `200`,
   iar cu `-H 'Range: bytes=0-99'` → `206`.

## 2. Domeniu / proxy (nginx pe gazdă → Caddy pe port exotic)

Caddy publică pe `127.0.0.1:${APP_PORT}` (implicit `28173`). În nginx-ul tău (`:80`/`:443`),
trimite `/unde-locuiesc-romanii/*` acolo, **păstrând calea completă** — Caddy se așteaptă la
prefix și îl decupează singur:

```nginx
location /unde-locuiesc-romanii/ {
    proxy_pass http://127.0.0.1:28173;        # FĂRĂ „/" final → nu rescrie calea
    proxy_http_version 1.1;
    proxy_set_header Host              $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
}
```

⚠️ Dacă pui `proxy_pass http://127.0.0.1:28173/;` (cu „/" final), nginx decupează prefixul și
Caddy nu mai potrivește ruta — lasă-l **fără** slash. Cererile cu `Range` (parquet/zarr) trec nativ.

## 3. GitHub — redeploy la fiecare commit

Repo: `github.com/geospatialorg/unde-locuiesc-romanii`. Workflow: `.github/workflows/deploy.yml`
(la `push` pe `main`: build frontend → `rsync` pe VM → `docker compose up -d --build`).

**Secrets** (Settings → Secrets and variables → Actions → *Secrets*):
| nume | valoare |
|---|---|
| `SSH_HOST` | IP/host-ul VM-ului |
| `SSH_USER` | user de deploy |
| `SSH_KEY` | cheia privată SSH (cheia publică pusă în `~/.ssh/authorized_keys` pe VM) |
| `DEPLOY_PATH` | calea repo-ului pe VM (ex. `/home/deploy/unde-locuiesc-romanii`) |

**Variables** (același ecran → *Variables*):
| nume | valoare |
|---|---|
| `VITE_DATA_URL` | `https://services.geo-spatial.org/unde-locuiesc-romanii/data` |
| `VITE_ROUTING_URL` | `https://services.geo-spatial.org/unde-locuiesc-romanii/api` |

> `rsync --delete` exclude `data/` și `node_modules/`, deci datele de pe VM nu sunt atinse la deploy.

## 4. Cloudflare în față (pas ulterior)

Când adăugăm Cloudflare pe `geo-spatial.org`:
- proxy „orange cloud" pe subdomeniu;
- **Cache Rule**: cache-uiește `…/unde-locuiesc-romanii/data/*` (parquet/zarr/geojson sunt statice),
  dar **exclude** `…/unde-locuiesc-romanii/data/live/*` (avertizări/prognoze proaspete). Caddy
  trimite deja `Cache-Control: no-cache` pe `live/` și `max-age=300` pe rest.

## 5. Actualizarea datelor

- `warnings`, `forecast`, `climate-cron` rulează continuu și scriu în `data/out/live` / re-asamblează
  produsele — nu depind de commit-uri.
- Reprocesare manuală după o sursă nouă: `docker compose run --rm pipeline python -m ulr_pipeline.run <pas> export validate`.

## Anexă — R2 (opțional, dacă vrei să scoți datele de pe VM)

`scripts/upload-data-r2.sh` + `infra/deploy/r2-cors.json` urcă `data/out` pe Cloudflare R2
(egress gratis). Atunci `VITE_DATA_URL` devine URL-ul public R2 (alt origin → CORS activ prin
`r2-cors.json`). Nefolosit în varianta „totul pe VM".
