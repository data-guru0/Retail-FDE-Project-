FROM python:3.13-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 curl \
  && rm -rf /var/lib/apt/lists/*
COPY . .
# torch + torchvision as a MATCHING pair from the pytorch CPU index, BEFORE the
# rest — otherwise `pip install .[ml]` pulls a torchvision built against a
# different torch and CLIP dies with "operator torchvision::nms does not exist".
RUN pip install --upgrade pip \
 && pip install --index-url https://download.pytorch.org/whl/cpu "torch==2.13.0" torchvision \
 && pip install -e ".[ml]"
CMD ["arq", "pipeline.worker.WorkerSettings"]
