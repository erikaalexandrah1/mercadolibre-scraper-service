"""Tests del split de mensajes por limite de caracteres (sin red ni navegador)."""
from app.shipping_messages import LIMITE_CARACTERES, dividir_mensaje, mensaje_courier, mensajes_para_courier


def test_courier_desconocido_no_tiene_template():
    assert mensaje_courier("pedidosya") is None


def test_courier_case_insensitive():
    assert mensaje_courier("MRW") == mensaje_courier("mrw")


def test_dividir_mensaje_corto_no_se_parte():
    assert dividir_mensaje("una linea corta") == ["una linea corta"]


def test_dividir_mensaje_respeta_el_limite():
    texto = "\n".join(f"linea {i} " + "x" * 50 for i in range(10))
    partes = dividir_mensaje(texto, limite=100)
    assert all(len(p) <= 100 for p in partes)
    # No se pierde contenido: todas las lineas originales siguen presentes.
    assert "\n".join(partes).count("linea 0") == 1
    assert "\n".join(partes).count("linea 9") == 1


def test_dividir_mensaje_nunca_corta_a_mitad_de_linea():
    texto = "AAAA\n" + "B" * (LIMITE_CARACTERES - 2) + "\nCCCC"
    partes = dividir_mensaje(texto)
    # La linea larga del medio debe quedar entera en algun mensaje.
    assert any("B" * (LIMITE_CARACTERES - 2) in p for p in partes)


def test_mensajes_para_courier_desconocido_da_lista_vacia():
    assert mensajes_para_courier("no-existe") == []


def test_los_3_couriers_quedan_bajo_el_limite():
    for courier in ("mrw", "zoom", "domesa"):
        mensajes = mensajes_para_courier(courier)
        assert len(mensajes) > 0
        assert all(len(m) <= LIMITE_CARACTERES for m in mensajes)


def test_los_3_couriers_parten_en_exactamente_2_mensajes():
    for courier in ("mrw", "zoom", "domesa"):
        assert len(mensajes_para_courier(courier)) == 2
