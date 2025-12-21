# ===== ETAPA 1: Builder (instalación dependencias) =====
FROM python:3.11-slim AS builder

# Variables de entorno para pip
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Instalar dependencias del sistema solo para compilación
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copiar requirements y pip-tools si existen
COPY requirements.txt requirements-dev.txt* ./

# Instalar dependencias en capa separada para mejor caché
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    # Instalar solo runtime dependencies
    if [ -f "requirements.txt" ]; then \
      pip install --no-cache-dir --user -r requirements.txt; \
    fi && \
    # Instalar dev dependencies solo si existen
    if [ -f "requirements-dev.txt" ]; then \
      pip install --no-cache-dir --user -r requirements-dev.txt; \
    fi

# ===== ETAPA 2: Runtime (imagen final liviana) =====
FROM python:3.11-slim AS runtime

# Usuario no-root para seguridad
RUN groupadd -r appuser && \
    useradd --no-log-init -r -g appuser appuser && \
    # Crear directorios necesarios
    mkdir -p /app/uploads /home/appuser && \
    chown -R appuser:appuser /app /home/appuser

WORKDIR /app

# Copiar solo las dependencias instaladas desde builder
COPY --from=builder /root/.local /root/.local

# Dependencias runtime mínimas
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Para psycopg2
    libpq-dev \
    # Para debugging
    curl \
    # Para healthcheck
    netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

# Añadir .local/bin al PATH
ENV PATH=/root/.local/bin:$PATH \
    PYTHONPATH=/app \
    # FastAPI settings
    APP_MODULE=main:app \
    APP_HOST=0.0.0.0 \
    APP_PORT=8000 \
    # Python optimizations
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    # Para uvicorn workers
    WEB_CONCURRENCY=2 \
    MAX_WORKERS=4

# Cambiar a usuario no-root
USER appuser

# Copiar aplicación
COPY --chown=appuser:appuser . .

# Verificar estructura
RUN echo "=== Verificando estructura ===" && \
    ls -la && \
    echo "=== Requirements instalados ===" && \
    pip list && \
    echo "=== Python path ===" && \
    python -c "import sys; print(sys.path)"

# Healthcheck mejorado
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:${APP_PORT}/health || exit 1

EXPOSE 8000

# Comando de ejecución con opciones optimizadas
CMD ["sh", "-c", \
     "uvicorn ${APP_MODULE} \
     --host ${APP_HOST} \
     --port ${APP_PORT} \
     --workers ${WEB_CONCURRENCY} \
     --limit-concurrency ${MAX_WORKERS} \
     --timeout-keep-alive 30 \
     --no-access-log"]