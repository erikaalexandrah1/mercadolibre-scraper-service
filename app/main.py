"""
Punto de entrada del microservicio (FastAPI).

Rutas:
  GET  /health          -> estado del servicio y de Mongo
  POST /scrape          -> ejecuta un scraping y guarda en Mongo
  GET  /productos       -> lista productos ya guardados

Las rutas de scraping son sincronas a proposito: FastAPI las corre en un
threadpool, evitando bloquear el event loop con Playwright (API sincrona).
"""
from fastapi import Depends, FastAPI, Header, HTTPException, status

from app import __version__
from app.config import Settings, get_settings
from app.repository import ProductoRepository
from app.schemas import (
    BatchResultItem,
    BatchScrapeRequest,
    BatchScrapeResponse,
    Producto,
    ScrapeRequest,
    ScrapeResponse,
)
from app.scraper import MercadoLibreScraper

app = FastAPI(
    title="MercadoLibre Scraper Service",
    version=__version__,
    description="Microservicio que scrapea productos de MercadoLibre Venezuela.",
)


def verificar_api_key(
    x_api_key: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    """Exige el header X-API-Key si hay una API key configurada."""
    if settings.auth_enabled and x_api_key != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="API key invalida o ausente."
        )


@app.get("/health", tags=["infra"])
def health(settings: Settings = Depends(get_settings)) -> dict:
    """Devuelve el estado del servicio y la conectividad con Mongo."""
    estado_mongo = "ok"
    repo = None
    try:
        repo = ProductoRepository(settings)
        repo.ping()
    except Exception as e:  # noqa: BLE001 - queremos reportar cualquier fallo
        estado_mongo = f"error: {e}"
    finally:
        if repo:
            repo.close()
    return {"servicio": "ok", "version": __version__, "mongo": estado_mongo}


@app.post(
    "/scrape",
    response_model=ScrapeResponse,
    dependencies=[Depends(verificar_api_key)],
    tags=["scraping"],
)
def scrape(
    payload: ScrapeRequest,
    settings: Settings = Depends(get_settings),
) -> ScrapeResponse:
    """Ejecuta el scraping para una busqueda y persiste los resultados."""
    repo = ProductoRepository(settings)
    try:
        scraper = MercadoLibreScraper(settings)
        productos = scraper.run(
            query=payload.query, pages=payload.pages, max_items=payload.max_items
        )
        repo.guardar_muchos(productos)
    except FileNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))
    finally:
        repo.close()

    return ScrapeResponse(
        consulta=payload.query,
        total=len(productos),
        productos=[Producto(**p) for p in productos],
    )


@app.post(
    "/scrape/batch",
    response_model=BatchScrapeResponse,
    dependencies=[Depends(verificar_api_key)],
    tags=["scraping"],
)
def scrape_batch(
    payload: BatchScrapeRequest,
    settings: Settings = Depends(get_settings),
) -> BatchScrapeResponse:
    """
    Scrapea varias busquedas en una sola llamada y persiste todo.

    Pensado para que un backend externo con su propio cron envie el listado
    de terminos a monitorear (ej. una vez al dia). Si un termino falla, se
    reporta su error y se continua con los demas.
    """
    repo = ProductoRepository(settings)
    scraper = MercadoLibreScraper(settings)
    resultados: list[BatchResultItem] = []
    total_productos = 0
    try:
        for query in payload.queries:
            try:
                productos = scraper.run(
                    query=query, pages=payload.pages, max_items=payload.max_items
                )
                for p in productos:
                    p["consulta"] = query
                repo.guardar_muchos(productos)
                total_productos += len(productos)
                resultados.append(BatchResultItem(consulta=query, total=len(productos)))
            except Exception as e:  # noqa: BLE001 - un termino no debe tumbar el batch
                resultados.append(BatchResultItem(consulta=query, total=0, error=str(e)))
    finally:
        repo.close()

    return BatchScrapeResponse(
        total_queries=len(payload.queries),
        total_productos=total_productos,
        resultados=resultados,
    )


@app.get(
    "/productos",
    response_model=list[Producto],
    dependencies=[Depends(verificar_api_key)],
    tags=["scraping"],
)
def listar_productos(
    consulta: str | None = None,
    limite: int = 50,
    settings: Settings = Depends(get_settings),
) -> list[Producto]:
    """Lista los productos ya guardados, opcionalmente filtrando por consulta."""
    repo = ProductoRepository(settings)
    try:
        docs = repo.listar(consulta=consulta, limite=limite)
    finally:
        repo.close()
    return [Producto(**d) for d in docs]
