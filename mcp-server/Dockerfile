FROM python:3.13-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 curl \
  && rm -rf /var/lib/apt/lists/*
COPY . .
RUN pip install --upgrade pip && pip install -e .
HEALTHCHECK --interval=10s --timeout=5s --retries=12 \
  CMD python -c "import socket; socket.create_connection(('localhost',8070),3)" || exit 1
EXPOSE 8070
CMD ["python", "server.py"]
