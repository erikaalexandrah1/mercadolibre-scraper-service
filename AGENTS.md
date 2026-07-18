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
  main.py        # FastAPI: rutas /health, /scrape, /productos
  config.py      # Settings (pydantic-settings) desde variables de entorno
  schemas.py     # Contratos de la API (Pydantic)
  browser.py     # Fabrica de BrowserContext de Playwright (anti-deteccion)
  scraper.py     # MercadoLibreScraper: logica de scraping
  repository.py  # ProductoRepository: acceso a MongoDB
scripts/
  login.py       # Genera storage_state.json — SOLO se corre en local
tests/
  test_scraper.py
```

Regla de dependencias: `main` -> (`scraper`, `repository`, `schemas`, `config`).
`scraper` -> `browser` -> `config`. No romper esta direccion (nada de que
`repository` importe `scraper`, etc.).

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
- Playwright **sincrono**; las rutas de FastAPI que scrapean se declaran con
  `def` (no `async def`) para que corran en el threadpool sin bloquear el loop.
- Acceso a datos solo via `ProductoRepository`; no usar pymongo directo fuera de ahi.
- Configuracion solo via `app/config.py` (nunca leer `os.environ` disperso).
- Guardado en Mongo con **upsert por `link`** para no duplicar.

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
