"""
Fabrica de navegadores Playwright con configuracion anti-deteccion.

Centraliza la creacion del navegador y del contexto para que la logica de
scraping no repita la configuracion de sesion + disfraz de automatizacion.
"""
import os
from contextlib import contextmanager

from playwright.sync_api import BrowserContext, sync_playwright

from app.config import Settings

# Script que se inyecta antes de cargar cada pagina para ocultar la senal
# 'navigator.webdriver' que delata a los navegadores automatizados.
_STEALTH_SCRIPT = "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"


@contextmanager
def browser_context(settings: Settings):
    """
    Context manager que entrega un BrowserContext listo para scrapear:
      - navegador headless (configurable)
      - sesion cargada desde storage_state_path
      - user-agent realista y senal de automatizacion oculta

    Uso:
        with browser_context(settings) as context:
            page = context.new_page()
            ...
    """
    if not os.path.exists(settings.storage_state_path):
        raise FileNotFoundError(
            f"No existe el archivo de sesion '{settings.storage_state_path}'. "
            "Genera la sesion con scripts/login.py y montalo en el servidor."
        )

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=settings.headless,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        context: BrowserContext = browser.new_context(
            storage_state=settings.storage_state_path,
            user_agent=settings.user_agent,
            locale="es-VE",
            viewport={"width": 1366, "height": 900},
        )
        context.set_default_navigation_timeout(settings.nav_timeout_ms)
        context.add_init_script(_STEALTH_SCRIPT)
        try:
            yield context
        finally:
            browser.close()
