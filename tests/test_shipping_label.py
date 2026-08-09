"""
Tests del parseo/validacion de la respuesta del VLM (sin llamar a OpenRouter
de verdad: se alimenta directamente el JSON que el modelo devolveria, para no
depender de una API key ni de red en el runner de tests).
"""
import json

from app.shipping_label import ShippingLabelReader


def _json(**campos) -> str:
    return json.dumps(campos)


def test_nombre_con_simbolo_roto_de_impresora_se_limpia():
    """
    Defecto conocido de la impresora termica de ZOOM: una vocal acentuada en
    mayuscula sale como un simbolo roto en vez de la letra. El VLM deberia
    reconstruir la letra (ver _PROMPT), pero si igual queda un simbolo,
    _limpiar_nombre lo saca sin pegar las dos mitades de la palabra. Se
    prueba con varios nombres y simbolos distintos para confirmar que no es
    un caso hardcodeado a un nombre puntual.
    """
    reader = ShippingLabelReader()
    casos = [
        ("JOS � GUALDRON", "JOS GUALDRON"),
        ("MAR ⌐ A PEREZ", "MAR A PEREZ"),
        ("ANDR □ S RONDON", "ANDR S RONDON"),
        ("MU□OZ CASTILLO", "MUOZ CASTILLO"),
    ]
    for nombre_crudo, esperado in casos:
        resultado = reader._parsear(
            _json(courier="zoom", recipient_name=nombre_crudo, recipient_phone="04121623093", recipient_address="Y")
        )
        assert resultado.recipient_name == esperado, f"fallo con {nombre_crudo!r}"


def test_nombre_con_guion_y_apostrofe_no_se_toca():
    """Guiones y apostrofes son validos en nombres reales, no son ruido de impresora."""
    reader = ShippingLabelReader()
    resultado = reader._parsear(
        _json(courier="zoom", recipient_name="MARÍA-JOSÉ O'BRIEN", recipient_phone="04121623093", recipient_address="Y")
    )
    assert resultado.recipient_name == "MARÍA-JOSÉ O'BRIEN"


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


# --- direccion: mismo defecto de impresora que el nombre, pero mas permisiva ---


def test_direccion_con_simbolo_roto_de_impresora_se_limpia():
    reader = ShippingLabelReader()
    resultado = reader._parsear(
        _json(
            courier="zoom",
            recipient_name="X",
            recipient_phone="04121623093",
            recipient_address="SECTOR SOC□PO, PARR □ QUIA CENTRO",
        )
    )
    assert resultado.recipient_address == "SECTOR SOCPO, PARR QUIA CENTRO"


def test_direccion_conserva_puntuacion_y_abreviaturas_legitimas():
    """N/D, C.C., ZP:, punto y coma, guiones — todo esto es real en direcciones venezolanas."""
    reader = ShippingLabelReader()
    direccion_cruda = "CR 9 ENTRE CALLES 3 Y 4, C.C. GALERIAS NIVEL P.B LOCAL NRO 6 — N/D; PARROQUIA: ; MUNICIPIO: BARINAS; ZONA POSTAL: N/D"
    resultado = reader._parsear(
        _json(courier="zoom", recipient_name="X", recipient_phone="04121623093", recipient_address=direccion_cruda)
    )
    assert resultado.recipient_address == direccion_cruda


def test_direccion_vacia_tras_limpiar_marca_faltante():
    """Si despues de sacar el ruido no queda nada, se trata como no leida, no como texto vacio 'valido'."""
    reader = ShippingLabelReader()
    resultado = reader._parsear(
        _json(courier="zoom", recipient_name="X", recipient_phone="04121623093", recipient_address="■■■□□□")
    )
    assert resultado.ok is False
    assert "recipient_address" in resultado.missing_fields


# --- telefono: solo digitos, y rechazar numeros claramente truncados ---


def test_telefono_con_separadores_se_reduce_a_digitos():
    reader = ShippingLabelReader()
    resultado = reader._parsear(
        _json(courier="zoom", recipient_name="X", recipient_phone="0414-014-2022", recipient_address="Y")
    )
    assert resultado.recipient_phone == "04140142022"


def test_telefono_muy_corto_se_trata_como_no_leido():
    """Un telefono de 5 digitos es casi seguro un numero truncado, no uno real."""
    reader = ShippingLabelReader()
    resultado = reader._parsear(_json(courier="zoom", recipient_name="X", recipient_phone="04121", recipient_address="Y"))
    assert resultado.recipient_phone == ""
    assert "recipient_phone" in resultado.missing_fields


def test_telefono_de_10_digitos_sin_cero_inicial_se_acepta():
    reader = ShippingLabelReader()
    resultado = reader._parsear(_json(courier="zoom", recipient_name="X", recipient_phone="4121623093", recipient_address="Y"))
    assert resultado.recipient_phone == "4121623093"


# --- JSON envuelto en markdown u otro texto alrededor (el modelo no siempre obedece "sin markdown") ---


def test_json_envuelto_en_fence_de_markdown_se_extrae():
    reader = ShippingLabelReader()
    respuesta = '```json\n{"courier": "zoom", "recipient_name": "X", "recipient_phone": "04121623093", "recipient_address": "Y"}\n```'
    resultado = reader._parsear(respuesta)
    assert resultado.ok is True
    assert resultado.courier == "zoom"


def test_json_con_texto_alrededor_se_extrae():
    reader = ShippingLabelReader()
    respuesta = 'Aca esta el resultado: {"courier": "mrw", "recipient_name": "X", "recipient_phone": "04121623093", "recipient_address": "Y"} espero que sirva'
    resultado = reader._parsear(respuesta)
    assert resultado.ok is True
    assert resultado.courier == "mrw"


# --- respuesta malformada de OpenRouter (no deberia tirar un KeyError/IndexError crudo) ---


def test_extraer_contenido_sin_choices_da_error_legible():
    import pytest

    reader = ShippingLabelReader()
    with pytest.raises(RuntimeError, match="choices"):
        reader._extraer_contenido({"choices": []})


def test_extraer_contenido_sin_content_da_error_legible():
    import pytest

    reader = ShippingLabelReader()
    with pytest.raises(RuntimeError, match="vacia"):
        reader._extraer_contenido({"choices": [{"message": {}}]})


def test_extraer_contenido_ok():
    reader = ShippingLabelReader()
    contenido = reader._extraer_contenido({"choices": [{"message": {"content": '{"courier": "zoom"}'}}]})
    assert contenido == '{"courier": "zoom"}'
