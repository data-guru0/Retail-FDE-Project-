FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1

WORKDIR /app

# system deps: libpq for psycopg, curl for the container healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
      libpq5 curl && rm -rf /var/lib/apt/lists/*

COPY . .
RUN pip install --upgrade pip && pip install -e .

HEALTHCHECK --interval=10s --timeout=5s --retries=12 \
  CMD curl -fsS http://localhost:8000/health || exit 1

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
