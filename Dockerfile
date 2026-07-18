# Imagen oficial de Playwright: trae Chromium + todas las dependencias del SO
# ya instaladas, evitando el error tipico de "faltan librerias" en el servidor.
FROM mcr.microsoft.com/playwright/python:v1.45.0-jammy

WORKDIR /app

# Instalar dependencias primero para aprovechar la cache de capas de Docker.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el codigo de la aplicacion.
COPY app ./app
COPY scripts ./scripts

# El archivo de sesion NO va en la imagen: se monta como volumen/secreto
# en Coolify (ver README). Por defecto se busca en /app/storage_state.json.
ENV STORAGE_STATE_PATH=/app/storage_state.json
ENV HEADLESS=true

EXPOSE 8000

# Arranca el servidor. Un solo worker: el scraping es pesado y con estado de
# navegador; escalar se hace con mas replicas, no con mas workers.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
