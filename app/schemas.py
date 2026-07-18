"""Modelos de datos (contratos de la API) usando Pydantic."""
from pydantic import BaseModel, Field


class ScrapeRequest(BaseModel):
    """Cuerpo de la peticion para iniciar un scraping."""

    query: str = Field(..., min_length=1, description="Termino a buscar, ej: 'laptop'")
    pages: int = Field(1, ge=1, le=10, description="Numero de paginas de resultados a recorrer")
    max_items: int = Field(10, ge=1, le=50, description="Maximo de productos por pagina")


class Producto(BaseModel):
    """Un producto scrapeado de MercadoLibre."""

    titulo: str
    precio: str
    moneda: str
    envio_gratis: bool
    cantidad_vendida: int
    vendedor: str
    tienda_oficial: bool
    link: str
    consulta: str


class ScrapeResponse(BaseModel):
    """Respuesta de un scraping completado."""

    consulta: str
    total: int
    productos: list[Producto]


class BatchScrapeRequest(BaseModel):
    """Cuerpo para scrapear varias busquedas en una sola llamada.

    Pensado para que un backend externo (con su propio cron) envie el
    listado de terminos a monitorear una vez al dia.
    """

    queries: list[str] = Field(..., min_length=1, description="Lista de terminos a buscar")
    pages: int = Field(1, ge=1, le=10, description="Paginas de resultados por termino")
    max_items: int = Field(20, ge=1, le=50, description="Maximo de productos por pagina")


class BatchResultItem(BaseModel):
    """Resultado del scraping de un termino dentro de un batch."""

    consulta: str
    total: int
    error: str | None = None


class BatchScrapeResponse(BaseModel):
    """Resumen de un batch: cuantos productos se obtuvieron por termino."""

    total_queries: int
    total_productos: int
    resultados: list[BatchResultItem]
