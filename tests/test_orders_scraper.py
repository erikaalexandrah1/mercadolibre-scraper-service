"""
Tests unitarios del parseo de ordenes de MercadoEnvios (sin red ni navegador).
"""
from app.orders_scraper import (
    _orden_id_de_href,
    _parse_cantidad,
    _parse_fecha_venta,
    _parse_monto,
    _split_label_value,
    _username_de_href_perfil,
)


def test_split_label_value_simple():
    assert _split_label_value("Quien recibe:  Allán Vicente Carvajal Castellanos") == (
        "Quien recibe",
        "Allán Vicente Carvajal Castellanos",
    )


def test_split_label_value_con_dos_puntos_en_el_valor():
    # partition() corta en el PRIMER ':', el resto queda en el valor.
    assert _split_label_value("Nota: Horario: 9 a 5") == ("Nota", "Horario: 9 a 5")


def test_split_label_value_sin_dos_puntos():
    assert _split_label_value("Sin label") == ("Sin label", "")


def test_parse_cantidad():
    assert _parse_cantidad("Cantidad: 1") == 1
    assert _parse_cantidad("Cantidad: 12") == 12


def test_parse_cantidad_sin_numero():
    assert _parse_cantidad("Cantidad: ") == 0


def test_parse_monto_bolivares():
    assert _parse_monto("Bs. 4.492,72") == "4492.72"


def test_parse_monto_dolares():
    assert _parse_monto("($. 6,00)") == "6.00"


def test_parse_monto_sin_match():
    assert _parse_monto("gratis") == ""


def test_parse_fecha_venta():
    assert _parse_fecha_venta(" Venta #2000017700234554 - 1/8/26 ") == "1/8/26"


def test_parse_fecha_venta_sin_match():
    assert _parse_fecha_venta("texto sin formato esperado") == ""


def test_orden_id_de_href():
    assert _orden_id_de_href("/vendedor/orden/2000017700234554") == "2000017700234554"


def test_orden_id_de_href_absoluta():
    assert (
        _orden_id_de_href("https://www.mercadoenvios.com.ve/vendedor/orden/2000017699166528")
        == "2000017699166528"
    )


def test_orden_id_de_href_sin_match():
    assert _orden_id_de_href("/vendedor/dashboard") == ""


def test_username_de_href_perfil():
    assert (
        _username_de_href_perfil("https://www.mercadolibre.com.ve/perfil/comprador/ALLANCARVAJAL")
        == "ALLANCARVAJAL"
    )


def test_username_de_href_perfil_con_query():
    assert (
        _username_de_href_perfil("https://www.mercadolibre.com.ve/perfil/comprador/K-MILIN?from=x")
        == "K-MILIN"
    )


def test_username_de_href_perfil_sin_match():
    assert _username_de_href_perfil("https://www.mercadolibre.com.ve/otra-cosa") == ""
