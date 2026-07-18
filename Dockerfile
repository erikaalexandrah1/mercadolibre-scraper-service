# Imagen oficial de Playwright: trae Chromium + dependencias del SO ya listas.
FROM mcr.microsoft.com/playwright/python:v1.45.0-jammy

WORKDIR /app

# 1) Instalar torch en su build de CPU (evita descargar ~2GB de CUDA).
#    Al fijar la misma version que requirements.txt, pip la da por satisfecha.
RUN pip install --no-cache-dir torch==2.3.1 --index-url https://download.pytorch.org/whl/cpu

# 2) Resto de dependencias (torch ya esta instalado, pip lo omite).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 3) Pre-descargar el modelo CLIP en build para que el primer request no espere.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('clip-ViT-B-32')"

# Copiar el codigo de la aplicacion.
COPY app ./app
COPY scripts ./scripts

# El archivo de sesion NO va en la imagen: se monta como volumen/secreto
# en Coolify (ver README). Por defecto se busca en /app/storage_state.json.
ENV STORAGE_STATE_PATH=/app/storage_state.json
ENV HEADLESS=true

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
