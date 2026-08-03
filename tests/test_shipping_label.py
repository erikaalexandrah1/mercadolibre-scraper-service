"""
Tests del parseo de guias de envio (sin OCR real: usa el texto que Tesseract
efectivamente devolvio al correr contra dos fotos reales, para no depender
de una imagen ni de tener tesseract instalado en el runner de tests).
"""
from app.shipping_label import ShippingLabelReader

_OCR_ZOOM_1 = """¿00M 1693679981

temitente: ERIKA ALEXANDRA HERNANDEZ ZURILLA
Jrigen: Z00M LA URBINA Rel.:
destinatario: EDDIS ENRIQUE PADRON COLINA(Tel.04121623093/4

Jestino: CARRETERA H CENTRO COMERCIAL BORJAS LOCAL 6 Y 7 — N/D; PARR
e ; MUNICIPIO: ; CABIMAS; ZULIA; VENEZUELA; ZONA POSTA

A 0 0000

31/07/2026
"""

_OCR_ZOOM_2 = """Z00M 1693627154 MAR
Remitente: ERIKA ALEXANDRA HERNANDEZ ZURILLA

Orlgen: Z00M LA URBINA Ref.:

Destinatario: RONALD FERRER(Tel,04126633488/4126633488)

Destino: AV. 3 NRO 10-98, ESQUINA 11 C.C. LAS AURORAS, NIVEL P.B LOC

N C.
L 9. — N/D; PARROQUIA: ; MUNICIPIO: : LOS PUERTOS DE ALTAG
RACIA; : ZULIA; VENEZUELA; ZONA POSTAL: N/D

A

31/07/2026
"""

_OCR_SIN_COURIER_RECONOCIBLE = "algo que no tiene ningun courier conocido"


def test_courier_zoom_con_o_confundida_por_cero():
    reader = ShippingLabelReader()
    resultado = reader._parsear(_OCR_ZOOM_1)
    assert resultado.courier == "zoom"


def test_destinatario_nombre_y_telefono_guia_1():
    reader = ShippingLabelReader()
    resultado = reader._parsear(_OCR_ZOOM_1)
    assert resultado.recipient_name == "EDDIS ENRIQUE PADRON COLINA"
    assert resultado.recipient_phone == "04121623093"


def test_destinatario_nombre_completo_no_se_pierde_guia_2():
    reader = ShippingLabelReader()
    resultado = reader._parsear(_OCR_ZOOM_2)
    assert resultado.recipient_name == "RONALD FERRER"
    assert resultado.recipient_phone == "04126633488"


def test_direccion_no_se_corta_en_el_primer_salto_de_linea():
    reader = ShippingLabelReader()
    resultado = reader._parsear(_OCR_ZOOM_2)
    # La direccion real sigue despues de un salto de linea ("LOC" -> "N C." -> "L 9...").
    assert "AURORAS" in resultado.recipient_address
    assert "ALTAG" in resultado.recipient_address


def test_direccion_con_d_confundida_por_j():
    reader = ShippingLabelReader()
    resultado = reader._parsear(_OCR_ZOOM_1)
    assert "CARRETERA H CENTRO COMERCIAL BORJAS" in resultado.recipient_address


def test_resultado_ok_cuando_estan_los_4_campos():
    reader = ShippingLabelReader()
    resultado = reader._parsear(_OCR_ZOOM_2)
    assert resultado.ok is True
    assert resultado.missing_fields == []


def test_resultado_no_ok_sin_courier_reconocible():
    reader = ShippingLabelReader()
    resultado = reader._parsear(_OCR_SIN_COURIER_RECONOCIBLE)
    assert resultado.ok is False
    assert "courier" in resultado.missing_fields
    assert "recipient_name" in resultado.missing_fields
