FROM python:3.12-slim

RUN pip install --no-cache-dir fastapi uvicorn "psycopg[binary]"

COPY main.py /app/main.py
WORKDIR /app
ENV PYTHONUNBUFFERED=1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
