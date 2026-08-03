"""
Templates de mensaje post-envio (uno por courier) y el split automatico por
el limite de caracteres del chat de Mercado Libre (350 por mensaje).

El split es generico (corta por lineas, no a mano por courier): junta lineas
completas hasta quedarse justo debajo del limite, y arranca un mensaje nuevo
cuando la proxima linea no entra. Esto reproduce solo, para cualquier
courier, el mismo split en 2 mensajes (info de envio / garantia) sin tener
que hardcodear "el primero es esto, el segundo es esto otro" por courier.

El limite se deja en 340 (no 350) porque el conteo de caracteres en el
navegador (UTF-16) y en Python difieren para algunos emoji fuera del BMP
(🔸 cuenta 1 en Python, 2 en el navegador) — el margen evita que un mensaje
que "entra" para Python quede rechazado por el textarea real.
"""

LIMITE_CARACTERES = 340

_GARANTIA = (
    "🔸Recuerde que cuenta con 3 días de garantía por defecto de fabrica una vez recibido. "
    "Por favor pruebe sus artículos una vez recibidos.\n"
    "🔸Muchas gracias 😁🙌🏻"
)

TEMPLATES: dict[str, str] = {
    "mrw": (
        "A continuación anexamos su guía de envío por MRW.\n"
        "🔸Su pedido puede demorar entre 24 a 48 horas en llegar si se encuentra en Caracas y 72 horas hábiles en el resto del país.\n"
        "🔸Puede realizar el seguimiento de su envío con el número de tracking (el que sale en negritas) a través de la página www.mrwve.com o escribiendo al WhatsApp +584242566482.\n"
        f"{_GARANTIA}"
    ),
    "zoom": (
        "A continuación anexamos su guía de envío por Zoom.\n"
        "🔸Su pedido puede demorar entre 24 a 48 horas en llegar si se encuentra en Caracas y 72 horas hábiles en el resto del país.\n"
        "🔸Puede realizar el seguimiento de su envío con el número de tracking a través de la página https://zoom.red/\n"
        f"{_GARANTIA}"
    ),
    "domesa": (
        "A continuación anexamos su guía de envío por Domesa.\n"
        "🔸Su pedido puede demorar entre 24 a 48 horas en llegar si se encuentra en Caracas y 72 horas hábiles en el resto del país.\n"
        "🔸Puede realizar el seguimiento de su envío con el número de tracking a través de la página www.portal.domesa.com.ve\n"
        f"{_GARANTIA}"
    ),
}


def mensaje_courier(courier: str) -> str | None:
    """Template completo (sin partir) para el courier, o None si no se reconoce."""
    return TEMPLATES.get((courier or "").strip().lower())


def dividir_mensaje(texto: str, limite: int = LIMITE_CARACTERES) -> list[str]:
    """
    Parte un texto en mensajes que entren en `limite` caracteres cada uno,
    cortando solo entre lineas completas (nunca a mitad de una linea/emoji).
    """
    lineas = texto.split("\n")
    mensajes: list[str] = []
    actual = ""

    for linea in lineas:
        candidato = f"{actual}\n{linea}" if actual else linea
        if len(candidato) <= limite:
            actual = candidato
        else:
            if actual:
                mensajes.append(actual)
            actual = linea

    if actual:
        mensajes.append(actual)

    return mensajes


def mensajes_para_courier(courier: str) -> list[str]:
    """Mensajes ya partidos y listos para mandar, para el courier dado (o [] si no se reconoce)."""
    plantilla = mensaje_courier(courier)
    if not plantilla:
        return []
    return dividir_mensaje(plantilla)
