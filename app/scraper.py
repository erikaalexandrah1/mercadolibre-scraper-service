"""
Logica de scraping de MercadoLibre Venezuela.

Flujo (imita a un usuario real para no ser bloqueado):
  1. Entra a la home con la sesion guardada.
  2. Escribe la busqueda en el buscador y da Enter.
  3. Recolecta los links de producto de la pagina de resultados.
  4. Entra a cada producto y extrae los campos.
"""
import re

from playwright.sync_api import BrowserContext, Page

from app.config import Settings
from app.browser import browser_context

HOME = "https://www.mercadolibre.com.ve"


def _texto(nodo, selector: str) -> str:
    el = nodo.query_selector(selector)
    return el.inner_text().strip() if el else ""


def _parsear_cantidad_vendida(texto_sub: str) -> int:
    """De 'Nuevo | +5 vendidos' o '10 vendidos' extrae el numero entero."""
    m = re.search(r"([\d\.]+)\s*vendido", texto_sub, re.IGNORECASE)
    return int(m.group(1).replace(".", "")) if m else 0


def _limpiar_vendedor(texto_titulo: str) -> str:
    """Quita el prefijo 'Vendido por' que muestran los vendedores no oficiales."""
    return re.sub(r"^Vendido por\s+", "", texto_titulo, flags=re.IGNORECASE).strip()


def _sin_duplicados(items: list[str]) -> list[str]:
    """Elimina duplicados conservando el orden de aparicion."""
    vistos: set[str] = set()
    unicos: list[str] = []
    for it in items:
        if it not in vistos:
            vistos.add(it)
            unicos.append(it)
    return unicos


class MercadoLibreScraper:
    """Scraper de resultados de busqueda de MercadoLibre Venezuela."""

    def __init__(self, settings: Settings):
        self._settings = settings

    def run(self, query: str, pages: int = 1, max_items: int = 10) -> list[dict]:
        """Ejecuta el scraping completo y devuelve la lista de productos."""
        productos: list[dict] = []
        with browser_context(self._settings) as context:
            page = context.new_page()
            self._buscar(page, query)

            # 1) Recorrer las paginas de resultados juntando todos los links.
            links: list[str] = []
            for n in range(pages):
                links.extend(self._recolectar_links(page, max_items))
                if n < pages - 1 and not self._ir_siguiente_pagina(page):
                    break  # no hay mas paginas
            links = _sin_duplicados(links)

            # 2) Entrar a cada producto y extraer los datos.
            for link in links:
                datos = self._scrapear_producto(page, link)
                datos["consulta"] = query
                productos.append(datos)
        return productos

    # --- pasos internos ---

    def _buscar(self, page: Page, query: str) -> None:
        """Va a la home y usa el buscador como un usuario real."""
        page.goto(HOME, wait_until="domcontentloaded")
        page.wait_for_timeout(2500)
        caja = page.query_selector("input.nav-search-input") or page.query_selector(
            "input[name='as_word']"
        )
        if not caja:
            raise RuntimeError(
                "No se encontro el buscador. La sesion pudo expirar; "
                "regenera storage_state.json con scripts/login.py."
            )
        caja.fill(query)
        caja.press("Enter")
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(3500)

    def _recolectar_links(self, page: Page, limite: int) -> list[str]:
        links: list[str] = []
        for a in page.query_selector_all("a.poly-component__title"):
            href = a.get_attribute("href")
            if href and href.startswith("http"):
                links.append(href.split("#")[0])
            if len(links) >= limite:
                break
        return links

    def _scrapear_producto(self, page: Page, url: str) -> dict:
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_timeout(1200)

        titulo = _texto(page, "h1.ui-pdp-title")
        moneda = _texto(page, ".ui-pdp-price__second-line .andes-money-amount__currency-symbol")
        entero = _texto(page, ".ui-pdp-price__second-line .andes-money-amount__fraction")
        precio = entero.replace(".", "") if entero else ""

        subtitulo = _texto(page, ".ui-pdp-subtitle") or _texto(page, ".ui-pdp-header__subtitle")
        cantidad_vendida = _parsear_cantidad_vendida(subtitulo)

        cuerpo = page.inner_text("body")
        envio_gratis = bool(re.search(r"env[ií]o\s+gratis", cuerpo, re.IGNORECASE))

        vendedor = _limpiar_vendedor(_texto(page, ".ui-seller-data-header__title"))
        # Las tiendas oficiales enlazan a /tienda/... con 'official_store_id' y
        # muestran un banner; los vendedores comunes no.
        tienda_oficial = bool(
            page.query_selector(".ui-seller-data a[href*='official_store_id=']")
            or page.query_selector(".ui-seller-data-banner__container")
        )

        return {
            "titulo": titulo,
            "precio": precio,
            "moneda": moneda,
            "envio_gratis": envio_gratis,
            "cantidad_vendida": cantidad_vendida,
            "vendedor": vendedor,
            "tienda_oficial": tienda_oficial,
            "link": url,
        }

    def _ir_siguiente_pagina(self, page: Page) -> bool:
        boton = page.query_selector("a.andes-pagination__link[title='Siguiente']")
        if not boton:
            return False
        boton.click()
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(2500)
        return True
