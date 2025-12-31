# ===== ETAPA 1: Builder multi-stage optimizado =====
FROM python:3.11-slim AS builder

WORKDIR /app

# Instalar SOLO lo necesario para compilar dependencias
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    python3-dev \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copiar requirements primero (para mejor cache)
COPY requirements.txt .

# Crear venv e instalar dependencias
RUN python -m venv /opt/venv && \
    /opt/venv/bin/pip install --no-cache-dir --upgrade pip && \
    /opt/venv/bin/pip install --no-cache-dir --no-deps -r requirements.txt && \
    /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

# ===== ETAPA 2: Runtime ultra ligero =====
FROM python:3.11-alpine3.18 AS runtime
# O usar debian:bullseye-slim si alpine da problemas

# Variables de entorno tempranas
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH="/app" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    APP_MODULE="main:app" \
    APP_HOST="0.0.0.0" \
    APP_PORT="8000" \
    UPLOADS_DIR="/app/uploads"

# Crear usuario y directorios en Alpine
RUN addgroup -S appuser && adduser -S appuser -G appuser && \
    mkdir -p ${UPLOADS_DIR} && \
    chown -R appuser:appuser /app && \
    chmod 755 ${UPLOADS_DIR}

WORKDIR /app

# Instalar SOLO dependencias runtime necesarias
# Primero, paquetes runtime de Python
RUN apk add --no-cache \
    # Dependencias de sistema mínimas
    libpq \
    curl \
    # Runtime para Pillow y procesamiento de imágenes
    jpeg-dev \
    zlib-dev \
    libwebp-dev \
    libheif-dev \
    # FFmpeg mínimo (solo lo necesario)
    ffmpeg-libs \
    # Para algunas bibliotecas Python
    libstdc++

# Si necesitas ffmpeg binario completo (solo si tu app lo llama)
RUN apk add --no-cache ffmpeg

# Copiar virtual environment desde builder
COPY --from=builder /opt/venv /opt/venv

# Copiar SOLO lo necesario de la aplicación
COPY --chown=appuser:appuser app/ /app/

# Cambiar a usuario no-root
USER appuser

# Healthcheck ligero
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:${APP_PORT}/health || exit 1

EXPOSE 8000

CMD ["sh", "-c", "uvicorn ${APP_MODULE} --host ${APP_HOST} --port ${APP_PORT}"]