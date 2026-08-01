FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    osmium-tool osm2pgrouting gdal-bin postgresql-client curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY import.sh mapconfig.xml /import/
RUN chmod +x /import/import.sh

CMD ["/import/import.sh"]
