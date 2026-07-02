FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    unixodbc-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ backend/
COPY utilsPrj/ utilsPrj/
COPY worker/ worker/
COPY static/ static/

# Chat Insight
COPY d2chat/ d2chat/
COPY d2insight/ d2insight/
COPY d2shared/ d2shared/

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

CMD ["python", "-m", "worker.main"]
