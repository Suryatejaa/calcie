FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV CALCIE_SYNC_DB_PATH=/data/sync_server.db

WORKDIR /app

COPY calcie_cloud/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY calcie_cloud /app/calcie_cloud
RUN mkdir -p /data

EXPOSE 8000

CMD ["sh", "-c", "uvicorn calcie_cloud.server:app --host 0.0.0.0 --port ${PORT:-8000}"]
