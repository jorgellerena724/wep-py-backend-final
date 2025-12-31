# ===== ETAPA 1: Builder =====
FROM python:3.11-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN python -m venv /opt/venv && \
    /opt/venv/bin/pip install --no-cache-dir --upgrade pip && \
    /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

# ===== ETAPA 2: Runtime =====
FROM python:3.11-slim AS runtime

# Crear usuario
RUN groupadd -g 1000 appuser && \
    useradd -u 1000 -g appuser -s /bin/bash -m appuser

WORKDIR /app

# Dependencias
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libpq-dev \
    curl \
    libjpeg-dev \
    libpng-dev \
    libwebp-dev \
    libheif-dev \
    && rm -rf /var/lib/apt/lists/*

# Copiar venv
COPY --from=builder /opt/venv /opt/venv

# === CARPETA UPLOADS CON 777 ===
RUN mkdir -p /app/uploads && \
    chmod 777 /app/uploads

# Variables
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH="/app" \
    PYTHONUNBUFFERED=1 \
    APP_MODULE="main:app" \
    APP_HOST="0.0.0.0" \
    APP_PORT="8000"

# Copiar app
COPY . .

# Verificar permisos
RUN echo "Permisos de /app/uploads: $(stat -c "%a" /app/uploads)"

USER appuser

# Test rápido
RUN touch /app/uploads/test_777.txt && \
    echo "✅ Escritura OK" && \
    rm /app/uploads/test_777.txt

EXPOSE 8000

CMD ["sh", "-c", "uvicorn ${APP_MODULE} --host ${APP_HOST} --port ${APP_PORT}"]