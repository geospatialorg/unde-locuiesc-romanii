FROM python:3.12-slim

# libexpat1 pt. rasterio; ecCodes pt. GRIB; cron+tzdata pt. actualizările periodice
RUN apt-get update && apt-get install -y --no-install-recommends \
    libexpat1 libeccodes0 libeccodes-data cron tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src /app/src
COPY cron_entry.sh /app/cron_entry.sh
RUN chmod +x /app/cron_entry.sh
ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

CMD ["python", "-m", "ulr_pipeline.run", "all"]
