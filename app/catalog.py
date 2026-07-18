"""
Importacion del catalogo propio desde "Mis publicaciones".

Como el scraper esta logueado con la sesion del usuario, puede entrar a la
pagina de publicaciones, extraer los IDs de sus productos, y de cada ficha
publica sacar titulo + foto. Cada foto se vectoriza UNA vez (CLIP) y se guarda
en la coleccion 'references'.

La API publica de MercadoLibre (api.mercadolibre.com) esta bloqueada sin token,
por eso se hace por scraping de la ficha publica.
"""
import re
from datetime import date

from playwright.sync_api import Page

from app.browser import browser_context
from app.config import Settings
from app.embeddings import ImageEmbedder
from app.scraper import _extraer_imagen, _texto

PUBLICACIONES_URL = "https://www.mercadolibre.com.ve/publicaciones"


def _url_articulo(item_id: str) -> str:
    """Construye la URL de ficha publica a partir del ID (MLV560637663)."""
    digits = item_id.replace("MLV", "")
    return f"https://articulo.mercadolibre.com.ve/MLV-{digits}-_JM"


def _recolectar_ids(page: Page) -> list[str]:
    """IDs (MLVxxx) visibles en la pagina de publicaciones actual."""
    ids: list[str] = []
    vistos: set[str] = set()
    for a in page.query_selector_all("a[href*='itemId=MLV']"):
        m = re.search(r"itemId=(MLV\d+)", a.get_attribute("href") or "")
        if m and m.group(1) not in vistos:
            vistos.add(m.group(1))
            ids.append(m.group(1))
    return ids


def _siguiente_pagina_publicaciones(page: Page) -> bool:
    """Avanza a la siguiente pagina de publicaciones (paginacion por boton)."""
    boton = page.query_selector(
        "a.andes-pagination__link[title='Siguiente'], "
        "button[aria-label*='iguiente'], .andes-pagination__button--next a"
    )
    if not boton:
        return False
    try:
        boton.click()
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(3500)
        return True
    except Exception:
        return False


class CatalogImporter:
    """Importa el catalogo propio del usuario a la coleccion 'references'."""

    def __init__(self, settings: Settings, embedder: ImageEmbedder):
        self._settings = settings
        self._embedder = embedder

    def import_catalog(self, reference_repo, limit: int | None = None) -> dict:
        """
        Recorre las publicaciones, vectoriza cada foto y guarda referencias.

        Devuelve {'imported', 'total_found', 'errors'}.
        Si 'limit' se indica, solo importa esa cantidad (util para probar).
        """
        errors: list[str] = []
        imported = 0

        with browser_context(self._settings) as context:
            page = context.new_page()

            # 1) Juntar todos los IDs recorriendo las paginas de publicaciones.
            ids = self._recolectar_todos_los_ids(page, limit)

            # 2) Por cada ID: ficha publica -> titulo + foto -> embedding -> guardar.
            for item_id in ids:
                try:
                    ref = self._construir_referencia(page, item_id)
                    reference_repo.upsert(ref)
                    imported += 1
                except Exception as e:  # noqa: BLE001 - un item no debe tumbar todo
                    errors.append(f"{item_id}: {e}")

        return {"imported": imported, "total_found": len(ids), "errors": errors}

    # --- internos ---

    def _recolectar_todos_los_ids(self, page: Page, limit: int | None) -> list[str]:
        page.goto(PUBLICACIONES_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(5000)

        ids: list[str] = []
        vistos: set[str] = set()
        while True:
            for i in _recolectar_ids(page):
                if i not in vistos:
                    vistos.add(i)
                    ids.append(i)
            if limit is not None and len(ids) >= limit:
                return ids[:limit]
            if not _siguiente_pagina_publicaciones(page):
                break
        return ids

    def _construir_referencia(self, page: Page, item_id: str) -> dict:
        page.goto(_url_articulo(item_id), wait_until="domcontentloaded")
        page.wait_for_timeout(1500)

        title = _texto(page, "h1.ui-pdp-title")
        image_url = _extraer_imagen(page)
        if not image_url:
            raise RuntimeError("sin imagen en la ficha")

        embedding = self._embedder.embed_url(image_url)

        return {
            "ref_id": item_id,
            "title": title,
            # Por defecto se busca con el titulo; el usuario lo edita luego.
            "search_queries": [title] if title else [],
            "image_url": image_url,
            "embedding": embedding,
            "active": True,
            "updated_at": date.today().isoformat(),
        }
