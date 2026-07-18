"""
Genera la sesion de MercadoLibre (storage_state.json) — CORRER EN LOCAL.

Este script NO se corre en el servidor: abre un navegador visible para que
TU inicies sesion a mano (incluyendo el captcha). El archivo resultante se
sube luego al servidor como secreto / volumen persistente.

Uso:
    python -m scripts.login
    # o:  python scripts/login.py

Salida: storage_state.json en la raiz del proyecto.
"""
from playwright.sync_api import sync_playwright

STATE_FILE = "storage_state.json"
LOGIN_URL = "https://www.mercadolibre.com.ve"


def main() -> None:
    with sync_playwright() as p:
        # headless=False -> navegador visible para que puedas loguearte tu mismo.
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto(LOGIN_URL)

        print("\n" + "=" * 60)
        print("1. Inicia sesion en el navegador que se abrio.")
        print("2. Resuelve el captcha si aparece.")
        print("3. Cuando ya estes DENTRO, vuelve aqui y presiona ENTER.")
        print("=" * 60)
        input(">>> Presiona ENTER cuando hayas iniciado sesion... ")

        context.storage_state(path=STATE_FILE)
        print(f"\nSesion guardada en '{STATE_FILE}'.")
        print("Subela al servidor como archivo montado (ver README).")
        browser.close()


if __name__ == "__main__":
    main()
