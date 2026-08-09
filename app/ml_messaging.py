"""
Envio de guias de envio por el chat REAL de un comprador en MercadoLibre.

Flujo:
  1. Busca al comprador por username en ventas/omni/listado.
  2. Entra al chat de esa venta (link "Mensajes" de la fila).
  3. Adjunta la foto de la guia y la manda.
  4. Manda el/los mensaje(s) de texto correspondientes al courier.

Esto le escribe a un CLIENTE REAL — por eso en cada paso donde el resultado
no es inequivoco (0 o mas de 1 comprador con ese username visible, el boton
de enviar no se habilita, etc.) se corta con un error claro en vez de
adivinar o mandar algo a la persona equivocada.

Restriccion NO negociable heredada del resto del scraper: nada de URLs
directas de listado — se navega como un usuario real.
"""
import logging
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import Page

from app.browser import browser_context
from app.config import Settings
from app.shipping_messages import mensajes_para_courier

logger = logging.getLogger("app.ml_messaging")

VENTAS_URL = "https://www.mercadolibre.com.ve/ventas/omni/listado"
# Cuanto esperar a que el chat termine de re-renderizar tras adjuntar/enviar
# (el boton de enviar deja de estar disabled, el textarea se vuelve a montar).
_ESPERA_UI_MS = 8_000


class MlMessagingError(Exception):
    """Error esperable del flujo (comprador no encontrado, boton nunca se habilito, etc.)."""


class MlMessagingService:
    """Ubica a un comprador por username y le manda la guia + mensaje por su chat de ML."""

    def __init__(self, settings: Settings):
        self._settings = settings

    def send_shipping_guide(self, buyer_username: str, courier: str, image_bytes: bytes) -> dict:
        mensajes = mensajes_para_courier(courier)
        if not mensajes:
            raise MlMessagingError(f"Courier '{courier}' no reconocido; no hay template de mensaje.")

        with browser_context(self._settings) as context:
            page = context.new_page()
            mensajeria_href = self._buscar_comprador(page, buyer_username)
            page.goto(mensajeria_href, wait_until="domcontentloaded")
            page.wait_for_timeout(2000)

            self._adjuntar_y_enviar_imagen(page, image_bytes)
            enviados = 0
            for mensaje in mensajes:
                self._enviar_texto(page, mensaje)
                enviados += 1

        return {"ok": True, "messages_sent": enviados, "error": None}

    # --- ubicar al comprador ---

    def _buscar_comprador(self, page: Page, username: str) -> str:
        page.goto(VENTAS_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(2500)

        # Primero via el buscador de la pantalla (mas rapido si cubre username).
        caja = page.query_selector('input[data-andes-searchbox-input="true"]')
        if caja:
            caja.fill(username)
            caja.press("Enter")
            page.wait_for_timeout(2000)
            href = self._href_por_username_en_pagina(page, username)
            if href:
                return href
            # Sin resultados por busqueda: limpiamos y probamos el listado sin filtrar.
            caja.fill("")
            caja.press("Enter")
            page.wait_for_timeout(2000)

        href = self._href_por_username_en_pagina(page, username)
        if href:
            return href

        raise MlMessagingError(
            f"No encontre a '{username}' en ventas/omni/listado (ni buscando ni en el listado reciente)."
        )

    def _href_por_username_en_pagina(self, page: Page, username: str) -> str | None:
        filas = page.query_selector_all(".sc-row-marketplace")
        candidatos: list[str] = []
        for fila in filas:
            nick_el = fila.query_selector(".buyer-nickName")
            if not nick_el:
                continue
            nick = nick_el.inner_text().strip()
            if nick.lower() != username.lower():
                continue
            link_el = fila.query_selector('a[href*="/ventas/nueva/mensajeria/"]')
            href = link_el.get_attribute("href") if link_el else None
            if href:
                candidatos.append(href)

        candidatos = list(dict.fromkeys(candidatos))  # sin duplicados, conserva orden
        if len(candidatos) == 1:
            return candidatos[0]
        if len(candidatos) > 1:
            raise MlMessagingError(
                f"'{username}' matcheo {len(candidatos)} ventas distintas en el listado; ambiguo, no se manda nada."
            )
        return None

    # --- chat de la venta ---

    def _adjuntar_y_enviar_imagen(self, page: Page, image_bytes: bytes) -> None:
        # OJO: la pagina tiene OTRO input[type=file] escondido en el menu de
        # usuario (el de "Cambiar foto" del nav, presente en cualquier pagina
        # logueada) que aparece ANTES en el DOM. Hay que acotar al del chat.
        input_archivo = self._esperar_selector(page, '.message-input-box input[type="file"]', "el input de adjuntar archivo en el chat")
        input_archivo.set_input_files({"name": "guia.jpg", "mimeType": "image/jpeg", "buffer": image_bytes})
        self._esperar_boton_habilitado_y_enviar(page)

    def _enviar_texto(self, page: Page, texto: str) -> None:
        # OJO: tras mandar el adjunto (o el mensaje anterior), React re-renderiza
        # el chat y el <textarea> se desmonta y vuelve a montar; si lo buscamos
        # con query_selector en ese instante puede no existir todavia. Por eso
        # esperamos a que reaparezca en vez de asumir que ya esta.
        textarea = self._esperar_selector(page, 'textarea[placeholder="Escríbele al comprador"]', "el campo de texto del chat")
        textarea.fill(texto)
        self._esperar_boton_habilitado_y_enviar(page)

    def _esperar_selector(self, page: Page, selector: str, descripcion: str):
        try:
            return page.wait_for_selector(selector, timeout=_ESPERA_UI_MS)
        except Exception as e:
            ruta = self._capturar_diagnostico(page, f"selector_no_encontrado_{descripcion}")
            sufijo = f" Evidencia guardada en {ruta}." if ruta else ""
            raise MlMessagingError(f"No se encontro {descripcion} (timeout esperandolo).{sufijo}") from e

    def _esperar_boton_habilitado_y_enviar(self, page: Page) -> None:
        try:
            page.wait_for_selector(
                "#messageInputSubmit:not([disabled])", timeout=_ESPERA_UI_MS
            )
        except Exception as e:
            ruta = self._capturar_diagnostico(page, "boton_enviar_nunca_habilitado")
            sufijo = f" Evidencia guardada en {ruta}." if ruta else ""
            raise MlMessagingError(
                "El botón de enviar del chat nunca se habilitó después de adjuntar/escribir; "
                f"puede que hayan cambiado la interfaz del chat de ML.{sufijo}"
            ) from e

        boton = page.query_selector("#messageInputSubmit")
        boton.click()
        # Le damos tiempo a la UI a mandar el mensaje y resetear el input
        # antes del siguiente (adjunto o mensaje de texto).
        page.wait_for_timeout(2500)

    # --- diagnostico ---

    def _capturar_diagnostico(self, page: Page, motivo: str) -> str | None:
        """
        Guarda screenshot + HTML de la pagina en el momento del fallo, y
        loguea URL/titulo. Pensado para responder "sesion vencida (nos
        mando a un login) vs. ML cambio el chat (seguimos en la pagina
        correcta pero el selector ya no existe)" sin tener que adivinar.

        Nunca deja que un fallo ACA tape el error real: si algo de esto
        revienta (pagina ya cerrada, disco sin permiso, etc.), se loguea y
        se sigue de largo devolviendo None.
        """
        try:
            carpeta = Path(self._settings.debug_output_dir)
            carpeta.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            base = carpeta / f"{timestamp}_{motivo}"

            url_actual = page.url
            titulo_actual = page.title()
            logger.error(
                f"Fallo en chat de ML ({motivo}). url={url_actual!r} title={titulo_actual!r}"
            )

            screenshot_path = base.with_suffix(".png")
            page.screenshot(path=str(screenshot_path), full_page=True)

            html_path = base.with_suffix(".html")
            html_path.write_text(page.content(), encoding="utf-8")

            logger.error(f"Diagnostico guardado: {screenshot_path}, {html_path}")
            return str(base)
        except Exception as e:  # noqa: BLE001
            logger.error(f"No se pudo capturar diagnostico para '{motivo}': {e}")
            return None
        # Le damos tiempo a la UI a mandar el mensaje y resetear el input
        # antes del siguiente (adjunto o mensaje de texto).
        page.wait_for_timeout(2500)
