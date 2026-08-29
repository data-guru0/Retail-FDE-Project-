FROM python:3.13-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 curl \
  && rm -rf /var/lib/apt/lists/*
COPY . .
RUN pip install --upgrade pip && pip install -e .
# ML extras (torch/open-clip/sklearn/transformers) are installed at M4:
#   pip install ".[ml]"
CMD ["arq", "pipeline.worker.WorkerSettings"]
