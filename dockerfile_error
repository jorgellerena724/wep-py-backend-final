# ===== ETAPA 1: Builder optimizado =====
FROM python:3.11-slim-bookworm AS builder

WORKDIR /app

# Instalar SOLO compiladores necesarios
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    python3-dev \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Instalar en venv optimizado
RUN python -m venv /opt/venv && \
    /opt/venv/bin/pip install --no-cache-dir --upgrade pip && \
    /opt/venv/bin/pip install --no-cache-dir wheel && \
    /opt/venv/bin/pip install --no-cache-dir --no-build-isolation -r requirements.txt

# ===== ETAPA 2: Runtime mínimo =====
FROM debian:bookworm-slim AS runtime

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH="/app" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    APP_MODULE="main:app" \
    APP_HOST="0.0.0.0" \
    APP_PORT="8000" \
    UPLOADS_DIR="/app/uploads"

# Crear usuario y directorios
RUN groupadd -r appuser && \
    useradd -r -g appuser -s /bin/bash appuser && \
    mkdir -p ${UPLOADS_DIR} && \
    chown -R appuser:appuser /app && \
    chmod 755 ${UPLOADS_DIR}

WORKDIR /app

# Instalar SOLO lo absolutamente necesario
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Runtime para Python
    libpython3.11 \
    # Runtime para PostgreSQL
    libpq5 \
    # FFmpeg mínimo
    ffmpeg \
    # Para Pillow
    libjpeg62-turbo \
    libpng16-16 \
    libwebp7 \
    libheif1 \
    # Para curl healthcheck
    curl \
    ca-certificates \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copiar venv desde builder
COPY --from=builder /opt/venv /opt/venv

# Copiar aplicación (solo lo necesario)
COPY --chown=appuser:appuser . .

# Limpiar archivos innecesarios
RUN find /opt/venv -type f -name '*.pyc' -delete && \
    find /opt/venv -type d -name '__pycache__' -delete && \
    rm -rf /opt/venv/include && \
    rm -rf /opt/venv/share

USER appuser

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:${APP_PORT}/health || exit 1

EXPOSE 8000

CMD ["sh", "-c", "uvicorn ${APP_MODULE} --host ${APP_HOST} --port ${APP_PORT}"]