FROM python:3.12-slim

WORKDIR /app

# ── 시스템 패키지 + MS SQL ODBC 드라이버 설치 (루트 Dockerfile과 동일 — d2insight가
# MSSQL 데이터소스를 조회할 때 이 워커 컨테이너 안에서 직접 pyodbc로 접속한다) ──────
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc curl gnupg2 apt-transport-https ca-certificates \
    unixodbc-dev fonts-nanum \
    && curl -sSL https://packages.microsoft.com/config/debian/12/prod.list > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update -o Acquire::AllowInsecureRepositories=true \
    && ACCEPT_EULA=Y apt-get install -y --allow-unauthenticated msodbcsql17 \
    && rm -f /etc/apt/sources.list.d/mssql-release.list \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

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
