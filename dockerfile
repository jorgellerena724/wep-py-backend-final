# ===== ETAPA 1: Builder =====
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Instalar compiladores para dependencias Python
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copiar requirements
COPY requirements.txt ./

# Instalar dependencias en venv
RUN python -m venv /opt/venv && \
    /opt/venv/bin/pip install --no-cache-dir --upgrade pip && \
    /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

# ===== ETAPA 2: Runtime =====
FROM python:3.11-slim AS runtime

# Crear usuario y directorios con permisos CORREGIDOS
RUN groupadd -r appuser && \
    useradd -r -g appuser -s /bin/bash -m appuser && \
    mkdir -p /app/uploads && \
    mkdir -p /home/appuser && \
    chown -R appuser:appuser /app && \
    chown -R appuser:appuser /home/appuser && \
    chmod 755 /app && \
    chmod 755 /home/appuser

WORKDIR /app

# Copiar virtual environment
COPY --from=builder /opt/venv /opt/venv

# Instalar FFmpeg y dependencias runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libpq-dev \
    curl \
    # Para bibliotecas de imágenes
    libjpeg-dev \
    libpng-dev \
    libwebp-dev \
    libheif-dev \
    && rm -rf /var/lib/apt/lists/*

# Configurar entorno
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH="/app" \
    APP_MODULE="main:app" \
    APP_HOST="0.0.0.0" \
    APP_PORT="8000" \
    # Variable importante para el servicio de archivos
    UPLOADS="/app/uploads"

# Cambiar a usuario no-root ANTES de copiar archivos
USER appuser

# Copiar aplicación manteniendo ownership del usuario
COPY --chown=appuser:appuser . .

# VERIFICACIÓN DE PERMISOS (añadida)
RUN echo "=== Verificando permisos ===" && \
    echo "Usuario actual: $(whoami)" && \
    echo "UID: $(id -u)" && \
    echo "GID: $(id -g)" && \
    echo "" && \
    echo "Permisos de /app:" && \
    ls -la /app && \
    echo "" && \
    echo "Permisos de /app/uploads:" && \
    ls -la /app/uploads && \
    echo "" && \
    echo "¿Puedo escribir en /app/uploads?:" && \
    touch /app/uploads/test_permission.txt && \
    if [ $? -eq 0 ]; then \
        echo "✅ SI puedo escribir en /app/uploads" && \
        rm /app/uploads/test_permission.txt; \
    else \
        echo "❌ NO puedo escribir en /app/uploads"; \
    fi && \
    echo "" && \
    echo "Espacio disponible:" && \
    df -h /app

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:${APP_PORT}/health || exit 1

EXPOSE 8000

# Comando de ejecución
CMD ["sh", "-c", "uvicorn ${APP_MODULE} --host ${APP_HOST} --port ${APP_PORT}"]