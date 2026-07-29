FROM python:3.11-slim-bookworm

# ── 시스템 패키지 + MS SQL ODBC 드라이버 설치 ──────────────────────────
RUN apt-get update && apt-get install -y \
    curl gnupg2 apt-transport-https ca-certificates \
    build-essential unixodbc-dev \
    && curl -sSL https://packages.microsoft.com/config/debian/12/prod.list > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update -o Acquire::AllowInsecureRepositories=true \
    && ACCEPT_EULA=Y apt-get install -y --allow-unauthenticated msodbcsql17 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# ── Node.js 설치 (프론트엔드 빌드용) ───────────────────────────────────
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs

WORKDIR /app

# ── 백엔드 의존성 설치 ──────────────────────────────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── 전체 소스 복사 ─────────────────────────────────────────────────────
COPY . .

# ── 프론트엔드 빌드 ────────────────────────────────────────────────────
RUN cd frontend && npm install && npm run build

EXPOSE 8000

CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
