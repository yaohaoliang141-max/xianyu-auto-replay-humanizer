ARG PYTHON_IMAGE=python:3.12.13-slim-bookworm
FROM ${PYTHON_IMAGE}

ENV PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TZ=Asia/Shanghai

WORKDIR /app
RUN sed -i 's|http://deb.debian.org|https://mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl gcc fonts-dejavu-core fonts-liberation \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.lock.txt /tmp/requirements.lock.txt
RUN pip install --index-url https://pypi.tuna.tsinghua.edu.cn/simple --timeout 60 --retries 3 --no-cache-dir -r /tmp/requirements.lock.txt
RUN PLAYWRIGHT_DOWNLOAD_CONNECTION_TIMEOUT=60000 python -m playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/*
RUN PLAYWRIGHT_DOWNLOAD_CONNECTION_TIMEOUT=60000 python -m patchright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/*

COPY app/common /app/common
COPY app/backend-web /app/backend-web
COPY app/websocket /app/websocket
COPY app/scheduler /app/scheduler
COPY app/launcher /app/launcher
COPY scripts/cloud_entry.py scripts/cloud_health.py /app/
RUN mkdir -p /app/static /app/backups \
    /app/backend-web/browser_data /app/websocket/browser_data /app/scheduler/browser_data

ENTRYPOINT ["python", "/app/cloud_entry.py"]
CMD ["backend-web"]
