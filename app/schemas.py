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


# --- Ordenes pendientes de MercadoEnvios ---


class PendingOrder(BaseModel):
    """
    Una orden pendiente del Gestor de Ordenes de MercadoEnvios, con todos los
    datos necesarios para que el backend la registre como Purchase.

    Si 'error' viene seteado, el resto de los campos puede estar incompleto
    (fallo la extraccion de esa orden puntual; no tumba el resto del batch).
    """

    ml_order_id: str
    status: str = "Pendiente"
    order_date: str = ""

    product_title: str = ""
    quantity: int = 0
    product_image_url: str = ""
    product_ml_url: str = Field("", description="URL publica del producto en MercadoLibre, util para matchear contra Product.mlUrl")
    total_bs: str = ""
    total_usd: str = ""

    buyer_username: str = Field("", description="Username de MercadoLibre del comprador (ej. 'ALLANCARVAJAL'). Sirve para ubicarlo en mercadolibre.com.ve/ventas/omni/listado, que se busca por username y no por el nombre enmascarado.")

    shipping_company: str = Field("", description="Ej. 'Domesa', 'ZOOM' (texto crudo, sin normalizar)")
    shipping_method_label: str = ""
    recipient_name: str = ""
    recipient_address: str = ""
    recipient_reference: str = ""
    recipient_phone: str = ""
    agency_name: str = ""
    agency_address: str = ""

    billing_name: str = ""
    billing_id: str = ""

    payment_type: str = Field("", description="Ej. 'Pago móvil' (texto crudo, sin normalizar)")
    payment_bank_receiver: str = ""
    payment_bank_issuer: str = ""
    payment_reference: str = ""
    payment_date: str = ""
    payment_proof_base64: str | None = Field(
        None, description="Data URI base64 del comprobante de pago (imagen original, no un screenshot)"
    )

    error: str | None = None


class PendingOrdersResponse(BaseModel):
    """Resumen de una consulta de ordenes pendientes."""

    total: int
    orders: list[PendingOrder]


# --- Lectura de guias de envio (VLM via OpenRouter) ---


class ShippingLabelReadResponse(BaseModel):
    """
    Resultado de leer una foto de guia (ZOOM/MRW/Domesa) con un modelo de
    vision (OpenRouter).

    `ok=False` si no se pudieron sacar los 3 datos clave del destinatario
    (nombre, telefono, direccion) o no se reconocio el courier — en ese caso
    el llamador NO deberia usar estos datos para mandarle algo a un cliente
    real, y en cambio pedir revision manual.
    """

    ok: bool
    courier: str = Field("", description="'zoom' | 'mrw' | 'domesa' | '' si no se reconocio")
    recipient_name: str = ""
    recipient_phone: str = ""
    recipient_address: str = ""
    missing_fields: list[str] = Field(default_factory=list)
    raw_text: str = Field("", description="Respuesta cruda del modelo, util para depurar cuando falla el parseo")


class SendShippingGuideResponse(BaseModel):
    """
    Resultado de mandarle la guia + mensaje a un comprador por su chat real
    de Mercado Libre. `ok=False` con `error` describiendo por que no se pudo
    (comprador no encontrado, ambiguo, botón de enviar nunca se habilitó,
    etc.) — nunca se manda algo a medias sin avisar.
    """

    ok: bool
    messages_sent: int = 0
    error: str | None = None
