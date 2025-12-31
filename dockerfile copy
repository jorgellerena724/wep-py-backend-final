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

# Variables de entorno tempranas
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH="/app" \
    APP_MODULE="main:app" \
    APP_HOST="0.0.0.0" \
    APP_PORT="8000" \
    UPLOADS_DIR="/app/uploads"

# Crear usuario y grupo no-root
RUN groupadd -r appuser && \
    useradd -r -g appuser -s /bin/bash appuser && \
    # Crear directorio base de uploads como root
    mkdir -p ${UPLOADS_DIR} && \
    # Dar permisos completos a appuser sobre uploads
    chown -R appuser:appuser ${UPLOADS_DIR} && \
    chmod 755 ${UPLOADS_DIR}

WORKDIR /app

# Instalar FFmpeg y dependencias runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libpq-dev \
    curl \
    # Para procesamiento de imágenes
    libjpeg-dev \
    libpng-dev \
    libwebp-dev \
    libheif-dev \
    # Para manejo de archivos
    file \
    && rm -rf /var/lib/apt/lists/*

# Copiar virtual environment desde builder
COPY --from=builder /opt/venv /opt/venv

# Copiar aplicación como root primero
COPY . .

# === CONFIGURACIÓN CRÍTICA: Permisos para escritura dinámica ===
# Asegurar que appuser tenga control total sobre /app
RUN chown -R appuser:appuser /app && \
    # Permisos específicos para directorio de código
    chmod -R 755 /app && \
    # Permisos especiales para uploads (rwx para owner, rx para grupo/otros)
    chmod 755 ${UPLOADS_DIR} && \
    # Asegurar que todos los archivos Python sean legibles
    find /app -name "*.py" -exec chmod 644 {} \;

# Cambiar a usuario no-root para ejecución
USER appuser

# Verificación exhaustiva de permisos
RUN echo "=== VERIFICACIÓN DE PERMISOS ===" && \
    echo "" && \
    echo "📋 Información del usuario:" && \
    echo "  Usuario: $(whoami)" && \
    echo "  UID: $(id -u)" && \
    echo "  GID: $(id -g)" && \
    echo "  Grupos: $(id -Gn)" && \
    echo "" && \
    echo "📁 Permisos de directorios:" && \
    echo "  /app:" && ls -ld /app && \
    echo "  ${UPLOADS_DIR}:" && ls -ld ${UPLOADS_DIR} && \
    echo "" && \
    echo "🧪 Pruebas de escritura:" && \
    echo "  1. Crear archivo en ${UPLOADS_DIR}:" && \
    touch ${UPLOADS_DIR}/test_write.txt && \
    if [ $? -eq 0 ]; then echo "     ✅ Éxito"; rm ${UPLOADS_DIR}/test_write.txt; else echo "     ❌ Fallo"; fi && \
    echo "" && \
    echo "  2. Crear directorio cliente 'shirkasoft':" && \
    mkdir -p ${UPLOADS_DIR}/shirkasoft && \
    if [ $? -eq 0 ]; then echo "     ✅ Éxito"; rmdir ${UPLOADS_DIR}/shirkasoft; else echo "     ❌ Fallo"; fi && \
    echo "" && \
    echo "  3. Crear estructura anidada:" && \
    mkdir -p ${UPLOADS_DIR}/cliente1/subdir/otro && \
    if [ $? -eq 0 ]; then \
        echo "     ✅ Éxito"; \
        echo "  4. Crear archivo en estructura anidada:" && \
        touch ${UPLOADS_DIR}/cliente1/subdir/archivo.txt && \
        if [ $? -eq 0 ]; then echo "     ✅ Éxito"; else echo "     ❌ Fallo"; fi && \
        rm -rf ${UPLOADS_DIR}/cliente1; \
    else echo "     ❌ Fallo"; fi && \
    echo "" && \
    echo "💾 Espacio disponible:" && \
    df -h /app && \
    echo "" && \
    echo "=== VERIFICACIÓN COMPLETADA ==="

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:${APP_PORT}/health || exit 1

EXPOSE 8000

# Comando de ejecución
CMD ["sh", "-c", "uvicorn ${APP_MODULE} --host ${APP_HOST} --port ${APP_PORT}"]