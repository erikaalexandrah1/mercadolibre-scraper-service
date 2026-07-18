"""Modelos de datos (contratos de la API) usando Pydantic. Keys en ingles."""
from pydantic import BaseModel, Field


class ScrapeRequest(BaseModel):
    """Cuerpo de la peticion para iniciar un scraping."""

    query: str = Field(..., min_length=1, description="Termino a buscar, ej: 'laptop'")
    pages: int = Field(1, ge=1, le=10, description="Numero de paginas de resultados a recorrer")
    max_items: int = Field(10, ge=1, le=50, description="Maximo de productos por pagina")


class Product(BaseModel):
    """Un producto scrapeado de MercadoLibre."""

    title: str
    price: str
    currency: str
    free_shipping: bool
    sold_quantity: int
    seller: str
    official_store: bool
    image_url: str
    link: str
    query: str
    # Presentes solo cuando el producto se obtuvo comparando contra una referencia.
    ref_id: str | None = None
    similarity: float | None = None


class ScrapeResponse(BaseModel):
    """Respuesta de un scraping completado."""

    query: str
    total: int
    products: list[Product]


class BatchScrapeRequest(BaseModel):
    """Cuerpo para scrapear varias busquedas en una sola llamada."""

    queries: list[str] = Field(..., min_length=1, description="Lista de terminos a buscar")
    pages: int = Field(1, ge=1, le=10, description="Paginas de resultados por termino")
    max_items: int = Field(20, ge=1, le=50, description="Maximo de productos por pagina")


class BatchResultItem(BaseModel):
    """Resultado del scraping de un termino dentro de un batch."""

    query: str
    total: int
    error: str | None = None


class BatchScrapeResponse(BaseModel):
    """Resumen de un batch."""

    total_queries: int
    total_products: int
    results: list[BatchResultItem]


# --- Catalogo propio (referencias) ---


class Reference(BaseModel):
    """Un producto propio, importado desde 'Mis publicaciones'."""

    ref_id: str = Field(..., description="ID de la publicacion en MercadoLibre (MLVxxx)")
    title: str = Field(..., description="Titulo original de la publicacion (informativo)")
    search_queries: list[str] = Field(
        default_factory=list,
        description="Terminos que el scraper USA para buscar competencia (editable)",
    )
    image_url: str = ""
    active: bool = True
    updated_at: str = ""


class ImportSummary(BaseModel):
    """Resumen de una importacion del catalogo propio."""

    imported: int
    total_found: int
    errors: list[str] = Field(default_factory=list)


class ReferenceUpdate(BaseModel):
    """Campos editables de una referencia."""

    search_queries: list[str] | None = None
    active: bool | None = None


class CompareRequest(BaseModel):
    """Cuerpo para comparar el catalogo (o una referencia) contra la competencia."""

    ref_id: str | None = Field(
        default=None, description="Si se indica, compara solo esa referencia; si no, todas las activas"
    )
    pages: int = Field(1, ge=1, le=10, description="Paginas de resultados por termino de busqueda")
    max_items: int = Field(20, ge=1, le=50, description="Maximo de productos por pagina")


class CompareResultItem(BaseModel):
    """Resultado de comparar una referencia."""

    ref_id: str
    title: str
    products_found: int
    error: str | None = None


class CompareResponse(BaseModel):
    """Resumen de una comparacion."""

    references_processed: int
    total_products: int
    results: list[CompareResultItem]
