"""
Punto de entrada del microservicio (FastAPI).

Rutas:
  GET   /health                 -> estado del servicio y de Mongo
  POST  /scrape                 -> scrapea UNA busqueda y guarda
  POST  /scrape/batch           -> scrapea VARIAS busquedas (cron del backend)
  GET   /products               -> lista productos guardados (filtros)

  Catalogo propio + comparacion por imagen (CLIP):
  POST  /references/import      -> importa tus publicaciones (title+foto+embedding)
  GET   /references             -> lista tu catalogo
  PATCH /references/{ref_id}    -> edita search_queries / active
  POST  /compare                -> compara catalogo vs competencia por imagen

Las rutas de scraping/comparacion son sincronas: FastAPI las corre en un
threadpool, evitando bloquear el event loop con Playwright y CLIP (CPU).
"""
from fastapi import Depends, FastAPI, Header, HTTPException, status

from app import __version__
from app.comparison import ComparisonService
from app.catalog import CatalogImporter
from app.config import Settings, get_settings
from app.embeddings import ImageEmbedder
from app.repository import ProductRepository, ReferenceRepository
from app.schemas import (
    BatchResultItem,
    BatchScrapeRequest,
    BatchScrapeResponse,
    CompareRequest,
    CompareResponse,
    CompareResultItem,
    ImportSummary,
    Product,
    Reference,
    ReferenceUpdate,
    ScrapeRequest,
    ScrapeResponse,
)
from app.scraper import MercadoLibreScraper

app = FastAPI(
    title="MercadoLibre Scraper Service",
    version=__version__,
    description="Scrapea productos de MercadoLibre Venezuela y compara por imagen (CLIP).",
)


def verify_api_key(
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
    mongo_status = "ok"
    repo = None
    try:
        repo = ProductRepository(settings)
        repo.ping()
    except Exception as e:  # noqa: BLE001
        mongo_status = f"error: {e}"
    finally:
        if repo:
            repo.close()
    return {"service": "ok", "version": __version__, "mongo": mongo_status}


# --- Scraping directo ---


@app.post(
    "/scrape",
    response_model=ScrapeResponse,
    dependencies=[Depends(verify_api_key)],
    tags=["scraping"],
)
def scrape(payload: ScrapeRequest, settings: Settings = Depends(get_settings)) -> ScrapeResponse:
    """Ejecuta el scraping para una busqueda y persiste los resultados."""
    repo = ProductRepository(settings)
    try:
        products = MercadoLibreScraper(settings).run(
            query=payload.query, pages=payload.pages, max_items=payload.max_items
        )
        repo.save_many(products)
    except FileNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))
    finally:
        repo.close()
    return ScrapeResponse(
        query=payload.query, total=len(products), products=[Product(**p) for p in products]
    )


@app.post(
    "/scrape/batch",
    response_model=BatchScrapeResponse,
    dependencies=[Depends(verify_api_key)],
    tags=["scraping"],
)
def scrape_batch(
    payload: BatchScrapeRequest, settings: Settings = Depends(get_settings)
) -> BatchScrapeResponse:
    """Scrapea varias busquedas en una sola llamada (pensado para un cron externo)."""
    repo = ProductRepository(settings)
    scraper = MercadoLibreScraper(settings)
    results: list[BatchResultItem] = []
    total_products = 0
    try:
        for query in payload.queries:
            try:
                products = scraper.run(
                    query=query, pages=payload.pages, max_items=payload.max_items
                )
                repo.save_many(products)
                total_products += len(products)
                results.append(BatchResultItem(query=query, total=len(products)))
            except Exception as e:  # noqa: BLE001
                results.append(BatchResultItem(query=query, total=0, error=str(e)))
    finally:
        repo.close()
    return BatchScrapeResponse(
        total_queries=len(payload.queries), total_products=total_products, results=results
    )


@app.get(
    "/products",
    response_model=list[Product],
    dependencies=[Depends(verify_api_key)],
    tags=["scraping"],
)
def list_products(
    query: str | None = None,
    ref_id: str | None = None,
    min_similarity: float | None = None,
    limit: int = 50,
    settings: Settings = Depends(get_settings),
) -> list[Product]:
    """Lista productos guardados. Filtra por query, ref_id y/o similitud minima."""
    repo = ProductRepository(settings)
    try:
        docs = repo.list(
            query=query, ref_id=ref_id, min_similarity=min_similarity, limit=limit
        )
    finally:
        repo.close()
    return [Product(**d) for d in docs]


# --- Catalogo propio + comparacion por imagen ---


@app.post(
    "/references/import",
    response_model=ImportSummary,
    dependencies=[Depends(verify_api_key)],
    tags=["catalogo"],
)
def import_references(
    limit: int | None = None, settings: Settings = Depends(get_settings)
) -> ImportSummary:
    """
    Importa tu catalogo desde 'Mis publicaciones': title + foto + embedding CLIP.

    'limit' importa solo N productos (util para probar antes del catalogo completo).
    Es una operacion pesada (vectoriza cada foto); correr manualmente.
    """
    ref_repo = ReferenceRepository(settings)
    try:
        importer = CatalogImporter(settings, ImageEmbedder(settings))
        resumen = importer.import_catalog(ref_repo, limit=limit)
    except FileNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))
    finally:
        ref_repo.close()
    return ImportSummary(**resumen)


@app.get(
    "/references",
    response_model=list[Reference],
    dependencies=[Depends(verify_api_key)],
    tags=["catalogo"],
)
def list_references(
    only_active: bool = False, settings: Settings = Depends(get_settings)
) -> list[Reference]:
    """Lista tu catalogo importado (sin los embeddings, para respuestas livianas)."""
    ref_repo = ReferenceRepository(settings)
    try:
        docs = ref_repo.list(only_active=only_active)
    finally:
        ref_repo.close()
    return [Reference(**d) for d in docs]


@app.patch(
    "/references/{ref_id}",
    response_model=Reference,
    dependencies=[Depends(verify_api_key)],
    tags=["catalogo"],
)
def update_reference(
    ref_id: str, payload: ReferenceUpdate, settings: Settings = Depends(get_settings)
) -> Reference:
    """Edita los tags de busqueda (search_queries) o activa/desactiva una referencia."""
    ref_repo = ReferenceRepository(settings)
    try:
        doc = ref_repo.update(ref_id, payload.model_dump())
    finally:
        ref_repo.close()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Referencia no encontrada.")
    return Reference(**doc)


@app.post(
    "/compare",
    response_model=CompareResponse,
    dependencies=[Depends(verify_api_key)],
    tags=["catalogo"],
)
def compare(payload: CompareRequest, settings: Settings = Depends(get_settings)) -> CompareResponse:
    """
    Compara tu catalogo contra la competencia por imagen.

    Si se pasa 'ref_id', compara solo esa referencia; si no, todas las activas.
    Guarda cada producto con su 'ref_id' y 'similarity'.
    """
    ref_repo = ReferenceRepository(settings)
    prod_repo = ProductRepository(settings)
    try:
        if payload.ref_id:
            # Comparar una sola referencia (necesitamos su embedding).
            refs = [
                r for r in ref_repo.list_with_embedding(only_active=False)
                if r["ref_id"] == payload.ref_id
            ]
            if not refs:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Referencia no encontrada."
                )
        else:
            refs = ref_repo.list_with_embedding(only_active=True)

        service = ComparisonService(settings, ImageEmbedder(settings))
        results: list[CompareResultItem] = []
        total_products = 0
        for ref in refs:
            try:
                products = service.compare_reference(
                    ref, pages=payload.pages, max_items=payload.max_items
                )
                prod_repo.save_many(products)
                total_products += len(products)
                results.append(
                    CompareResultItem(
                        ref_id=ref["ref_id"], title=ref.get("title", ""),
                        products_found=len(products),
                    )
                )
            except Exception as e:  # noqa: BLE001
                results.append(
                    CompareResultItem(
                        ref_id=ref["ref_id"], title=ref.get("title", ""),
                        products_found=0, error=str(e),
                    )
                )
    except FileNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))
    finally:
        ref_repo.close()
        prod_repo.close()

    return CompareResponse(
        references_processed=len(refs), total_products=total_products, results=results
    )
