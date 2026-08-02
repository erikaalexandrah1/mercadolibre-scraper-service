"""
Genera la sesion de MercadoLibre + MercadoEnvios (storage_state.json) —
CORRER EN LOCAL.

Este script NO se corre en el servidor: abre un navegador visible para que
TU inicies sesion a mano (incluyendo el captcha). El archivo resultante se
sube luego al servidor como secreto / volumen persistente.

Las cookies son por dominio: iniciar sesion SOLO en mercadolibre.com.ve no
alcanza para scrapear mercadoenvios.com.ve (dominio distinto). Por eso este
script pasa por los DOS sitios en el mismo contexto de navegador antes de
guardar la sesion — si te saltas el paso 2, `/orders/pending` va a fallar con
"No se encontro el Gestor de Ordenes".

Uso:
    python -m scripts.login
    # o:  python scripts/login.py

Salida: storage_state.json en la raiz del proyecto.
"""
from playwright.sync_api import sync_playwright

STATE_FILE = "storage_state.json"
LOGIN_URL = "https://www.mercadolibre.com.ve"
MERCADOENVIOS_URL = "https://www.mercadoenvios.com.ve/vendedor/dashboard"


def main() -> None:
    with sync_playwright() as p:
        # headless=False -> navegador visible para que puedas loguearte tu mismo.
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto(LOGIN_URL)

        print("\n" + "=" * 60)
        print("PASO 1/2: MercadoLibre")
        print("1. Inicia sesion en el navegador que se abrio.")
        print("2. Resuelve el captcha si aparece.")
        print("3. Cuando ya estes DENTRO, vuelve aqui y presiona ENTER.")
        print("=" * 60)
        input(">>> Presiona ENTER cuando hayas iniciado sesion en MercadoLibre... ")

        page.goto(MERCADOENVIOS_URL)
        print("\n" + "=" * 60)
        print("PASO 2/2: MercadoEnvios (necesario para /orders/pending)")
        print("1. Si aparece un boton amarillo 'Ingresar con mi cuenta de")
        print("   Mercado Libre', hacele click (deberia entrar sin pedir")
        print("   captcha de nuevo, ya estas logueada en ML).")
        print("2. Confirma que llegaste al Dashboard / Gestor de ordenes.")
        print("3. Vuelve aqui y presiona ENTER.")
        print("=" * 60)
        input(">>> Presiona ENTER cuando hayas entrado a MercadoEnvios... ")

        context.storage_state(path=STATE_FILE)
        print(f"\nSesion guardada en '{STATE_FILE}' (incluye ambos dominios).")
        print("Subela al servidor como archivo montado (ver README).")
        browser.close()


if __name__ == "__main__":
    main()
