"""
Scraping del "Gestor de ordenes" de MercadoEnvios (pedidos pendientes de ML).

Flujo:
  1. Entra a /vendedor/orden?status=pending con la sesion guardada.
  2. Junta los links de detalle de cada orden pendiente (paginando si hace falta).
  3. Entra a cada detalle y extrae: producto, envio/facturacion y pago.

El comprobante de pago se muestra en la pagina como una imagen `blob:` (URL de
objeto del navegador, no una URL real). Por eso no se puede descargar con un
request aparte: se hace un `fetch()` de esa blob URL DENTRO del contexto de la
pagina (via page.evaluate) y se convierte a base64 ahi mismo. Esto trae el
archivo original que subio el comprador, no una foto de la pantalla.

Este scraper NO persiste nada: es lectura pura. El backend (powerleds-nest) es
quien decide que hacer con cada orden (matchear producto, evitar duplicados,
crear la Purchase).
"""
import base64
import logging
import re

from playwright.sync_api import BrowserContext, ElementHandle, Page

from app.browser import browser_context
from app.config import Settings
from app.scraper import _sin_duplicados

logger = logging.getLogger(__name__)

BASE = "https://www.mercadoenvios.com.ve"
LISTA_URL = f"{BASE}/vendedor/orden?status=pending"
DASHBOARD_URL = f"{BASE}/vendedor/dashboard"
_TEXTO_BOTON_SSO = "Ingresar con mi cuenta de Mercado Libre"


def _texto(nodo, selector: str) -> str:
    el = nodo.query_selector(selector)
    return el.inner_text().strip() if el else ""


def _attr(nodo, selector: str, atributo: str) -> str:
    el = nodo.query_selector(selector)
    return (el.get_attribute(atributo) or "") if el else ""


def _split_label_value(texto: str) -> tuple[str, str]:
    """De 'Quien recibe:  Allan Perez' saca ('Quien recibe', 'Allan Perez')."""
    if ":" not in texto:
        return texto.strip(), ""
    label, _, value = texto.partition(":")
    return label.strip(), value.strip()


def _parse_cantidad(texto: str) -> int:
    """De 'Cantidad: 1' saca 1."""
    m = re.search(r"(\d+)", texto)
    return int(m.group(1)) if m else 0


def _parse_monto(texto: str) -> str:
    """
    Saca el numero de un monto tipo 'Bs. 4.492,72' o '($. 6,00)' y lo deja en
    formato con punto decimal ('4492.72', '6.00'). '' si no matchea.
    """
    m = re.search(r"([\d.]+,\d{2})", texto)
    if not m:
        return ""
    return m.group(1).replace(".", "").replace(",", ".")


def _parse_fecha_venta(texto: str) -> str:
    """De ' Venta #2000017700234554 - 1/8/26 ' saca '1/8/26'."""
    m = re.search(r"-\s*(\S+)\s*$", texto.strip())
    return m.group(1) if m else ""


def _orden_id_de_href(href: str) -> str:
    """De '/vendedor/orden/2000017700234554' saca el ID."""
    m = re.search(r"/vendedor/orden/(\d+)", href or "")
    return m.group(1) if m else ""


def _username_de_href_perfil(href: str) -> str:
    """De '.../perfil/comprador/ALLANCARVAJAL' saca 'ALLANCARVAJAL'."""
    m = re.search(r"/perfil/comprador/([^/?#]+)", href or "")
    return m.group(1) if m else ""


class MercadoEnviosOrdersScraper:
    """Scraper del Gestor de Ordenes de MercadoEnvios (pedidos pendientes)."""

    def __init__(self, settings: Settings):
        self._settings = settings

    def run(self) -> list[dict]:
        """Recorre todas las ordenes pendientes y devuelve sus datos completos."""
        ordenes: list[dict] = []
        with browser_context(self._settings) as context:
            page = context.new_page()
            hrefs = self._listar_pendientes(page, context)
            for href in hrefs:
                try:
                    ordenes.append(self._extraer_detalle(page, href))
                except Exception as e:  # noqa: BLE001 - una orden no debe tumbar el resto
                    ordenes.append({"ml_order_id": _orden_id_de_href(href), "error": str(e)})
        return ordenes

    # --- lista ---

    def _listar_pendientes(self, page: Page, context: BrowserContext) -> list[str]:
        page.goto(LISTA_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(2500)

        if not page.query_selector("melienvios-vendedor-orden-lista-page"):
            if not self._reconectar_sesion_mercadoenvios(page, context):
                raise RuntimeError(
                    "No se encontro el Gestor de Ordenes y no se pudo re-vincular "
                    "mercadoenvios.com.ve automaticamente (la sesion de Mercado Libre "
                    "tambien parece haber expirado); regenera storage_state.json con "
                    "scripts/login.py (logueandote tambien ahi)."
                )
            page.goto(LISTA_URL, wait_until="domcontentloaded")
            page.wait_for_timeout(2500)
            if not page.query_selector("melienvios-vendedor-orden-lista-page"):
                raise RuntimeError(
                    "Se re-vinculo mercadoenvios.com.ve pero el Gestor de Ordenes "
                    "sigue sin aparecer; puede que haya cambiado la interfaz."
                )

        # Mostrar el maximo por pagina para minimizar la paginacion.
        selector_cantidad = page.query_selector("select#numberPerPage")
        if selector_cantidad:
            selector_cantidad.select_option("50")
            page.wait_for_timeout(1500)

        hrefs: list[str] = []
        while True:
            for a in page.query_selector_all("a.custom-link-order[href]"):
                href = a.get_attribute("href")
                if href:
                    hrefs.append(href)
            if not self._ir_siguiente_pagina(page):
                break
        return _sin_duplicados(hrefs)

    def _reconectar_sesion_mercadoenvios(self, page: Page, context: BrowserContext) -> bool:
        """
        La sesion de mercadoenvios.com.ve puede vencer por separado de la de
        mercadolibre.com.ve (dominio distinto, cookies distintas). Si la sesion
        de ML sigue viva, re-vincularla es solo un click en el boton amarillo
        de SSO ("Ingresar con mi cuenta de Mercado Libre") — sin captcha ni
        login manual. Si el boton no aparece, es que la sesion de ML tambien
        vencio y hace falta correr scripts/login.py de nuevo a mano.

        Si funciona, persiste la sesion refrescada en storage_state_path para
        que las proximas corridas ya la reutilicen sin repetir este paso.
        """
        page.goto(DASHBOARD_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(2500)

        boton = page.get_by_text(_TEXTO_BOTON_SSO, exact=False)
        if boton.count() == 0:
            return False

        logger.warning("Sesion de mercadoenvios vencida; re-vinculando via SSO con la sesion de ML existente...")
        boton.first.click()
        page.wait_for_timeout(4000)

        try:
            context.storage_state(path=self._settings.storage_state_path)
            logger.warning(f"Sesion de mercadoenvios re-vinculada; storage_state guardado en '{self._settings.storage_state_path}'.")
        except Exception as e:  # noqa: BLE001 - no debe tumbar la corrida actual si falla al persistir
            logger.warning(f"No se pudo persistir la sesion de mercadoenvios refrescada: {e}")

        return True

    def _ir_siguiente_pagina(self, page: Page) -> bool:
        boton = page.query_selector(
            "melienvios-paginator-component a[aria-label*='iguiente'], "
            "melienvios-paginator-component button[aria-label*='iguiente']"
        )
        if not boton:
            return False
        try:
            boton.click()
            page.wait_for_load_state("domcontentloaded")
            page.wait_for_timeout(2000)
            return True
        except Exception:
            return False

    # --- detalle ---

    def _extraer_detalle(self, page: Page, href: str) -> dict:
        url = href if href.startswith("http") else f"{BASE}{href}"

        # La app precarga el comprobante via una URL autenticada normal
        # (/api/v1/resources/voucher/...) apenas entra al detalle, sin que
        # haga falta clickear nada. La capturamos escuchando la red durante
        # la carga en vez de leer un blob: del <img> (que arranca vacio).
        comprobante_urls: list[str] = []

        def _on_response(response) -> None:
            if "/api/v1/resources/voucher/" in response.url:
                comprobante_urls.append(response.url)

        page.on("response", _on_response)
        try:
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_timeout(2500)
        finally:
            page.remove_listener("response", _on_response)

        return {
            "ml_order_id": _orden_id_de_href(href),
            "status": "Pendiente",
            **self._extraer_producto(page),
            **self._extraer_comprador(page),
            **self._extraer_envio(page),
            **self._extraer_factura(page),
            **self._extraer_pago(page, comprobante_urls[-1] if comprobante_urls else None),
            "error": None,
        }

    def _extraer_producto(self, page: Page) -> dict:
        bloque = page.query_selector(".product-details")
        if not bloque:
            raise RuntimeError("No se encontro el bloque de producto en el detalle de la orden.")
        return {
            "order_date": _parse_fecha_venta(_texto(bloque, ".product-description p.sub")),
            "product_title": _texto(bloque, "h2.bold"),
            "quantity": _parse_cantidad(_texto(bloque, ".product-description p.bold")),
            "product_image_url": _attr(bloque, ".product-image img", "src"),
            "product_ml_url": _attr(bloque, ".product-image a", "href"),
            "total_bs": _parse_monto(_texto(bloque, ".product-price h3")),
            "total_usd": _parse_monto(_texto(bloque, ".product-price h4")),
        }

    def _extraer_comprador(self, page: Page) -> dict:
        """
        Username del comprador (ej. 'ALLANCARVAJAL'), necesario para poder
        ubicarlo despues en mercadolibre.com.ve/ventas/omni/listado (esa
        pagina se busca por username, no por nombre completo enmascarado).
        """
        bloque = page.query_selector(".comprador-details")
        if not bloque:
            return {"buyer_username": ""}

        username = _username_de_href_perfil(_attr(bloque, "a.custom-link-order", "href"))
        if not username:
            # Respaldo: parsear el texto "Usuario: ALGO" si el link cambia de forma.
            texto = _texto(bloque, ".comprador-datos")
            m = re.search(r"Usuario:\s*(\S+)", texto)
            username = m.group(1) if m else ""

        return {"buyer_username": username}

    def _extraer_envio(self, page: Page) -> dict:
        bloque = self._bloque_por_titulo(page, "Método de envío")
        campos = self._pares_label_valor(bloque, ".details p") if bloque else {}
        return {
            "shipping_company": _attr(bloque, ".agencia-imagen img", "alt") if bloque else "",
            "shipping_method_label": _texto(bloque, ".description h3") if bloque else "",
            "recipient_name": campos.get("Quien recibe", ""),
            "recipient_address": campos.get("Dirección", ""),
            "recipient_reference": campos.get("Punto de referencia", ""),
            "recipient_phone": campos.get("Teléfono", ""),
            "agency_name": campos.get("Nombre de la agencia", ""),
            "agency_address": campos.get("Dirección de la agencia", ""),
        }

    def _extraer_factura(self, page: Page) -> dict:
        bloque = self._bloque_por_titulo(page, "Datos para la Factura")
        campos = self._pares_payment_step(bloque) if bloque else {}
        return {
            "billing_name": campos.get("Nombre para la factura", ""),
            "billing_id": campos.get("CI / RIF para la factura", ""),
        }

    def _extraer_pago(self, page: Page, comprobante_url: str | None) -> dict:
        bloque = self._bloque_por_titulo(page, "Datos de pago")
        if not bloque:
            return {
                "payment_type": "",
                "payment_bank_receiver": "",
                "payment_bank_issuer": "",
                "payment_reference": "",
                "payment_date": "",
                "payment_proof_base64": None,
            }
        campos = self._pares_payment_step(bloque)
        return {
            "payment_type": campos.get("Tipo de pago", ""),
            "payment_bank_receiver": campos.get("Banco receptor", ""),
            "payment_bank_issuer": campos.get("Banco emisor", ""),
            "payment_reference": campos.get("Código de referencia", ""),
            "payment_date": campos.get("Fecha de pago", ""),
            "payment_proof_base64": self._descargar_comprobante(page, comprobante_url),
        }

    # --- helpers de extraccion ---

    def _bloque_por_titulo(self, page: Page, titulo: str) -> ElementHandle | None:
        return page.query_selector(f'melienvios-labeled-list-component[title="{titulo}"]')

    def _pares_label_valor(self, bloque, selector: str) -> dict[str, str]:
        """Parsea pares '<p><span class="blue">Label:</span> Valor</p>'."""
        pares: dict[str, str] = {}
        for p in bloque.query_selector_all(selector):
            label, valor = _split_label_value(p.inner_text().strip())
            if label:
                pares[label] = valor
        return pares

    def _pares_payment_step(self, bloque) -> dict[str, str]:
        """
        Parsea pares '<div class="payment-step"><p class="label">/<p class="value">'.

        Algunas secciones (ej. 'Datos para la Factura') incluyen los dos
        puntos en la etiqueta ('Nombre para la factura:') y otras no ('Tipo
        de pago'); se normaliza sacando el ':' final para no depender de eso.
        """
        pares: dict[str, str] = {}
        for paso in bloque.query_selector_all(".payment-step"):
            etiqueta = _texto(paso, "p.label").rstrip(":").strip()
            if etiqueta:
                pares[etiqueta] = _texto(paso, "p.value")
        return pares

    def _descargar_comprobante(self, page: Page, url: str | None) -> str | None:
        """Descarga el comprobante (URL autenticada, no blob) y lo pasa a data URI base64."""
        if not url:
            return None
        try:
            resp = page.context.request.get(url)
            if not resp.ok:
                return None
            content_type = resp.headers.get("content-type", "image/jpeg")
            encoded = base64.b64encode(resp.body()).decode("ascii")
            return f"data:{content_type};base64,{encoded}"
        except Exception:
            return None
