FROM python:3.11-slim

# Usuario no-root
RUN groupadd -r appuser && useradd --no-log-init -r -g appuser appuser

WORKDIR /app

# Dependencias del sistema
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Instalar dependencias Python
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 🔧 CREAR DIRECTORIO UPLOADS CON PERMISOS
RUN mkdir -p /app/uploads && chown -R appuser:appuser /app/uploads

# Cambiar usuario
USER appuser

# Copiar aplicación
COPY --chown=appuser:appuser . .

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=5)" || exit 1

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]