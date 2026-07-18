# Guia para agentes de IA — mercadolibre-scraper-service

Contexto para asistentes de IA (Claude Code, Cursor, Copilot, etc.) que trabajen
en este repositorio. Leelo antes de proponer cambios.

## Que es este proyecto

Microservicio HTTP (FastAPI) que scrapea productos de **MercadoLibre Venezuela**
con Playwright y los guarda en **MongoDB**. Extrae por producto: `titulo`,
`precio`, `moneda`, `envio_gratis`, `cantidad_vendida`, `link`, `consulta`.

## Arquitectura (capas)

```
app/
  main.py        # FastAPI: rutas /health, /scrape, /products, /references, /compare
  config.py      # Settings (pydantic-settings) desde variables de entorno
  schemas.py     # Contratos de la API (Pydantic) — keys en INGLES
  browser.py     # Fabrica de BrowserContext de Playwright (anti-deteccion)
  scraper.py     # MercadoLibreScraper: logica de scraping
  repository.py  # ProductRepository / ReferenceRepository: acceso a MongoDB
  embeddings.py  # ImageEmbedder: CLIP ViT-B/32 (vectoriza imagenes) + coseno
  catalog.py     # CatalogImporter: importa "Mis publicaciones" -> references
  comparison.py  # ComparisonService: compara catalogo vs competencia por imagen
scripts/
  login.py       # Genera storage_state.json — SOLO se corre en local
tests/
  test_scraper.py, test_image.py
```

Regla de dependencias: `main` -> (`scraper`, `repository`, `catalog`,
`comparison`, `embeddings`, `schemas`, `config`). `scraper`/`catalog` ->
`browser` -> `config`. `comparison` -> (`scraper`, `embeddings`). No romper esta
direccion (nada de que `repository` importe `scraper`, etc.).

## Modelo de datos (Mongo)

- Coleccion `products`: productos scrapeados (upsert por `link`). Campos en
  ingles: `title, price, currency, free_shipping, sold_quantity, seller,
  official_store, image_url, link, query`. Si vienen de una comparacion,
  ademas `ref_id` y `similarity` (0..1, coseno de imagen).
- Coleccion `references`: catalogo propio (upsert por `ref_id`). Campos:
  `ref_id, title, search_queries (list, editable), image_url, embedding,
  active, updated_at`. `title` es informativo; **`search_queries` es lo que el
  scraper USA para buscar** (el usuario lo edita para no limitarse al titulo).

## Restricciones NO negociables (aprendidas a la fuerza)

1. **NO entrar por URL directa de listado** (`listado.mercadolibre.com.ve/...`):
   MercadoLibre responde "Hubo un error accediendo a esta pagina". SIEMPRE hay
   que ir a la home y usar el buscador (`_buscar()` en `scraper.py`).
2. **NO quitar el disfraz anti-deteccion** en `browser.py`: el `user_agent`
   realista + `--disable-blink-features=AutomationControlled` + ocultar
   `navigator.webdriver` son lo unico que evita el bloqueo del navegador headless.
3. **El login es manual y con captcha.** No intentar automatizar usuario/clave.
   La sesion (`storage_state.json`) se genera con `scripts/login.py` en local y
   se monta en el servidor. Nunca se commitea (esta en `.gitignore`).
4. **Los selectores CSS de MercadoLibre cambian seguido.** Si un campo sale
   vacio, casi siempre es eso: hay que reinspeccionar la pagina y actualizar los
   selectores en `scraper.py`. Los actuales usan componentes `poly-card` /
   `ui-pdp-*`.

## Convenciones de codigo

- Python 3.10+, type hints en firmas publicas.
- **Keys de datos en INGLES** (title, price, seller...), no espanol.
- Playwright **sincrono**; las rutas de FastAPI que scrapean/comparan se declaran
  con `def` (no `async def`) para que corran en el threadpool sin bloquear el loop.
- Acceso a datos solo via los repositorios; no usar pymongo directo fuera de ahi.
- Configuracion solo via `app/config.py` (nunca leer `os.environ` disperso).
- Guardado en Mongo con **upsert** (`link` en products, `ref_id` en references).
- El modelo CLIP se carga una sola vez (`@lru_cache` en `embeddings.py`).
- **Gotcha:** no nombrar un metodo `list` en una clase que luego use `list[...]`
  en anotaciones (tapa el builtin). `repository.py` usa
  `from __future__ import annotations` para evitarlo.

## Multi-tenancy (pendiente, futuro)

Hoy es single-tenant (solo la duena). Para comercializar: añadir `cliente_id`
a `products` y `references`, coleccion `clientes` con `api_key_hash`, y resolver
el tenant desde la API key. Dejar el codigo listo para ese eje.

## Como correr

```bash
pip install -r requirements.txt && playwright install chromium
python -m scripts.login          # local, una vez: genera storage_state.json
uvicorn app.main:app --reload    # levanta la API en :8000
pytest                           # tests unitarios (parseo, sin red)
```

## Al proponer cambios

- Mantener las 4 restricciones de arriba.
- Si tocas el parseo, actualiza/añade tests en `tests/test_scraper.py`.
- No introducir dependencias nuevas sin justificar.
