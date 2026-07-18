# MercadoLibre Scraper Service

Microservicio HTTP que scrapea productos de **MercadoLibre Venezuela** con
Playwright y los guarda en **MongoDB**. Pensado para desplegarse en un servidor
(Coolify) como backend.

Por cada producto extrae: `titulo`, `precio`, `moneda`, `envio_gratis`,
`cantidad_vendida`, `vendedor`, `tienda_oficial`, `link`, `consulta`.

---

## Tabla de contenidos

- [Arquitectura](#arquitectura)
- [API](#api)
- [Correr en local](#correr-en-local)
- [El login y la sesion (LEER)](#el-login-y-la-sesion-leer)
- [Despliegue en Coolify](#despliegue-en-coolify)
- [Operacion y mantenimiento](#operacion-y-mantenimiento)

---

## Arquitectura

```
app/
  main.py        # FastAPI: /health, /scrape, /productos
  config.py      # Configuracion desde variables de entorno
  schemas.py     # Modelos Pydantic (contratos de la API)
  browser.py     # Navegador Playwright con anti-deteccion + sesion
  scraper.py     # Logica de scraping
  repository.py  # Acceso a MongoDB (upsert por link, sin duplicados)
scripts/
  login.py       # Genera la sesion — SOLO en local
tests/
  test_scraper.py
```

Detalles de diseño y restricciones en [AGENTS.md](AGENTS.md).

## API

| Metodo | Ruta            | Descripcion                                       |
|--------|-----------------|---------------------------------------------------|
| GET    | `/health`       | Estado del servicio y de Mongo                    |
| POST   | `/scrape`       | Scrapea UNA busqueda y guarda en Mongo            |
| POST   | `/scrape/batch` | Scrapea VARIAS busquedas (para cron del backend)  |
| GET    | `/productos`    | Lista productos guardados                          |

Docs interactivas (Swagger) en `/docs` al levantar el servicio.

Ejemplo (una busqueda):

```bash
curl -X POST http://localhost:8000/scrape \
  -H "Content-Type: application/json" \
  -d '{"query": "laptop", "pages": 1, "max_items": 5}'
```

Ejemplo (batch — pensado para que tu backend lo llame con un cron diario):

```bash
curl -X POST http://localhost:8000/scrape/batch \
  -H "Content-Type: application/json" \
  -d '{"queries": ["laptop", "mouse gamer"], "pages": 1, "max_items": 20}'
```

`pages` recorre varias paginas de resultados; `max_items` es el tope de
productos por pagina (una pagina de MercadoLibre trae ~48). Si defines
`API_KEY`, añade el header `-H "X-API-Key: TU_CLAVE"`.

## Correr en local

Necesitas Docker (para Mongo) y Python 3.10+.

```bash
# 1. Dependencias
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
playwright install chromium

# 2. Generar la sesion (se abre un navegador, te logueas TU)
python -m scripts.login

# 3. Levantar Mongo
docker run -d --name mongo-scraper -p 27017:27017 -v mongo-data:/data/db mongo:7

# 4. Levantar la API
uvicorn app.main:app --reload
```

O todo junto con Docker Compose (usa tu `storage_state.json` ya generado):

```bash
docker compose up --build
```

## El login y la sesion (LEER)

Esta es la parte clave para operar el servicio.

- MercadoLibre Venezuela **exige login** para buscar, y el login **tiene
  captcha**. Por eso NO se puede automatizar usuario/clave.
- La solucion: `scripts/login.py` abre un navegador **visible** donde **tu**
  inicias sesion una vez. Guarda las cookies en `storage_state.json`.
- Ese archivo es tu "pase de acceso". El scraper lo reutiliza y **no vuelve a
  pedir login**.
- **`storage_state.json` NUNCA se sube a git** (esta en `.gitignore`): contiene
  tu sesion iniciada. Al servidor se sube aparte, como archivo montado / secreto.

### ¿El deploy en Coolify pide login cada vez? NO.

Siempre que el `storage_state.json` viva en un **volumen persistente** (no dentro
de la imagen Docker), los redeploys lo conservan y el servicio arranca sin pedir
nada. Solo tendras que regenerarlo cuando la sesion **expire** (semanas), y
volver a subir el archivo.

## Despliegue en Coolify

1. **Crear el recurso**: en Coolify, *New Resource → Application → desde este
   repo de GitHub*. Coolify detecta el `Dockerfile` y construye la imagen.

2. **MongoDB**: crea un recurso *Database → MongoDB* en el mismo proyecto.
   Copia su URI interna (algo como `mongodb://<user>:<pass>@<servicio>:27017`).

3. **Variables de entorno** (seccion *Environment Variables* de la app):
   ```
   MONGO_URI=mongodb://<host-interno-de-mongo>:27017
   MONGO_DB=mercadolibre
   MONGO_COLLECTION=productos
   STORAGE_STATE_PATH=/app/storage_state.json
   HEADLESS=true
   API_KEY=<una-clave-larga-y-secreta>
   ```

4. **Subir la sesion como archivo persistente** — dos opciones:

   - **Opcion A (recomendada) — File mount / Storage:** en la app, seccion
     *Storages → Add → File mount*. Destino: `/app/storage_state.json`. Pega el
     contenido de tu `storage_state.json` local. Coolify lo monta como archivo y
     **sobrevive a los redeploys**.

   - **Opcion B — Volumen persistente + subida manual:** monta un volumen en
     `/app` y copia el archivo por SSH/consola del contenedor una vez.

   > El objetivo en ambos casos: que `/app/storage_state.json` exista en runtime
   > y persista entre despliegues, SIN estar dentro de la imagen ni en git.

5. **Puerto**: la app expone `8000`. Configura el dominio/puerto en Coolify.

6. **Health check**: apunta el health check de Coolify a `GET /health`.

7. **Deploy**. Verifica con:
   ```bash
   curl https://TU-DOMINIO/health
   ```

## Operacion y mantenimiento

- **Renovar la sesion (cuando expire):**
  1. En local: `python -m scripts.login` (te logueas de nuevo).
  2. Copia el nuevo `storage_state.json`.
  3. En Coolify, actualiza el contenido del File mount del paso 4A.
  4. Redeploy (o reinicia el contenedor).

- **Sintoma de sesion expirada:** `/scrape` devuelve error "No se encontro el
  buscador..." o resultados vacios. -> Renueva la sesion.

- **Sintoma de selectores rotos:** `/scrape` responde 200 pero con campos
  vacios. -> Hay que actualizar los selectores en `app/scraper.py`.

- **Escalar:** una sola instancia procesa un scraping a la vez (Playwright es
  pesado). Para mas volumen, añade replicas en Coolify; todas comparten Mongo y
  la misma sesion montada.

- **Tests:** `pytest` (solo prueban el parseo, no requieren red ni navegador).

---

Licencia: uso interno.
