"""
Tests del parseo/validacion de la respuesta del VLM (sin llamar a OpenRouter
de verdad: se alimenta directamente el JSON que el modelo devolveria, para no
depender de una API key ni de red en el runner de tests).
"""
import json

from app.shipping_label import ShippingLabelReader


def _json(**campos) -> str:
    return json.dumps(campos)


def test_courier_reconocido():
    reader = ShippingLabelReader()
    resultado = reader._parsear(_json(courier="zoom", recipient_name="X", recipient_phone="04121623093", recipient_address="Y"))
    assert resultado.courier == "zoom"


def test_courier_no_reconocido_queda_vacio():
    reader = ShippingLabelReader()
    resultado = reader._parsear(_json(courier="fedex", recipient_name="X", recipient_phone="04121623093", recipient_address="Y"))
    assert resultado.courier == ""
    assert "courier" in resultado.missing_fields


def test_courier_null_queda_vacio():
    reader = ShippingLabelReader()
    resultado = reader._parsear(_json(courier=None, recipient_name="X", recipient_phone="04121623093", recipient_address="Y"))
    assert resultado.courier == ""
    assert "courier" in resultado.missing_fields


def test_campos_completos_da_ok():
    reader = ShippingLabelReader()
    resultado = reader._parsear(
        _json(
            courier="zoom",
            recipient_name="EDDIS ENRIQUE PADRON COLINA",
            recipient_phone="04121623093",
            recipient_address="CARRETERA H CENTRO COMERCIAL BORJAS LOCAL 6 Y 7, CABIMAS, ZULIA",
        )
    )
    assert resultado.ok is True
    assert resultado.missing_fields == []
    assert resultado.recipient_name == "EDDIS ENRIQUE PADRON COLINA"
    assert resultado.recipient_phone == "04121623093"


def test_telefono_null_por_baja_confianza_marca_faltante():
    """El modelo prefiere null a adivinar un telefono truncado."""
    reader = ShippingLabelReader()
    resultado = reader._parsear(
        _json(courier="mrw", recipient_name="WILLIAM AULAR", recipient_phone=None, recipient_address="TURMERO, ARAGUA")
    )
    assert resultado.ok is False
    assert resultado.missing_fields == ["recipient_phone"]


def test_direccion_vacia_marca_faltante():
    reader = ShippingLabelReader()
    resultado = reader._parsear(
        _json(courier="domesa", recipient_name="Alln Carvajal", recipient_phone="04244092227", recipient_address="")
    )
    assert resultado.ok is False
    assert "recipient_address" in resultado.missing_fields


def test_json_invalido_no_revienta_y_marca_todo_faltante():
    reader = ShippingLabelReader()
    resultado = reader._parsear("esto no es json")
    assert resultado.ok is False
    assert resultado.missing_fields == ["courier", "recipient_name", "recipient_phone", "recipient_address"]
    assert resultado.raw_text == "esto no es json"


def test_json_no_es_objeto_no_revienta():
    reader = ShippingLabelReader()
    resultado = reader._parsear("[1, 2, 3]")
    assert resultado.ok is False
    assert resultado.missing_fields == ["courier", "recipient_name", "recipient_phone", "recipient_address"]


def test_courier_en_mayusculas_se_normaliza():
    reader = ShippingLabelReader()
    resultado = reader._parsear(_json(courier="ZOOM", recipient_name="X", recipient_phone="04121623093", recipient_address="Y"))
    assert resultado.courier == "zoom"
