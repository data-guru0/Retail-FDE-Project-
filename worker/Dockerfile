FROM python:3.13-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 curl \
  && rm -rf /var/lib/apt/lists/*
COPY . .
# CPU-only torch from the pytorch CPU index keeps the image small and the resolve fast.
RUN pip install --upgrade pip \
 && pip install --index-url https://download.pytorch.org/whl/cpu torch==2.13.0 \
 && pip install -e ".[ml]"
CMD ["arq", "pipeline.worker.WorkerSettings"]
