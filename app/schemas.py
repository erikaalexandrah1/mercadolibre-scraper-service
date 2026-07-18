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
    link: str
    consulta: str


class ScrapeResponse(BaseModel):
    """Respuesta de un scraping completado."""

    consulta: str
    total: int
    productos: list[Producto]
