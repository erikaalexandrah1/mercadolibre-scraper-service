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

# Foto real donde la Z de "ZOOM" salio como "2" o "¿" (nunca como Z literal)
# y "Destino" salio como "eslino" (la T confundida con L).
_OCR_ZOOM_3_Z_COMO_2_Y_T_COMO_L = """¿00M

1693924875
semitente: ERIKA di HERNANDEZ ZURILLA
tigen: 200M LA URBIN

Ael.:

sestinatario: CAMILO SALGADOTel 04125575592/4125575592)
eslino: AY. PEDRO RUFFO FERRER, (.5. LOS TEQUES Ibn AS. SECTOR E
"AMBOR. — NID: PARROQUIA: ; MUNICIPIO: ; LOS TEQUES; MIRAND
« VENEZUELA: ZONA POSTAL: N/D

A 0
A

23/08/2026
"""


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


def test_courier_zoom_con_z_confundida_por_2_o_signo_de_interrogacion():
    reader = ShippingLabelReader()
    resultado = reader._parsear(_OCR_ZOOM_3_Z_COMO_2_Y_T_COMO_L)
    assert resultado.courier == "zoom"


def test_destinatario_guia_3_con_s_por_d_y_sin_espacio_antes_de_tel():
    reader = ShippingLabelReader()
    resultado = reader._parsear(_OCR_ZOOM_3_Z_COMO_2_Y_T_COMO_L)
    assert resultado.recipient_name == "CAMILO SALGADO"
    assert resultado.recipient_phone == "04125575592"


def test_direccion_guia_3_con_destino_leido_como_eslino():
    reader = ShippingLabelReader()
    resultado = reader._parsear(_OCR_ZOOM_3_Z_COMO_2_Y_T_COMO_L)
    assert "PEDRO RUFFO FERRER" in resultado.recipient_address


def test_resultado_ok_guia_3():
    reader = ShippingLabelReader()
    resultado = reader._parsear(_OCR_ZOOM_3_Z_COMO_2_Y_T_COMO_L)
    assert resultado.ok is True
    assert resultado.missing_fields == []


# Foto real de una guia de MRW. Formato totalmente distinto a Zoom: 'DEST:'
# (no 'Destinatario:') trae nombre+cedula sin telefono, y el telefono del
# destinatario esta pegado al bloque anterior 'DESTINO:' (oficina de
# entrega), no al nombre. El logo 'MRW' es un watermark, no sale como texto.
_OCR_MRW_1 = """Y

CRiN

TR
012000511000773

UA

R2RARD4 | 114241
DESTINO: RETIRAR POR OF ICIMA
0511000 TURMERO ZONA

1 .
INDUSTRIAL

SEMITENTE LAURA ZURILLA

=o0 GEN n:i20600 A IoRrEiNa
ORISEN 1 20694 LA UREIMA

1LF:04125913710

pesT: WILLIAM AULAR V-11820181

IRMERO, C.C. INTI RCOMUNAL CENTER LOCAL NR
PRE SECTOR LA MORITA TURMERO, TURMERO PQ: SAMAN DE GUERE MNCP
SANTIAGO MARIÑO EDO: ARAGUA CP 1P -10-237-25-101.
npo: SOBRE 500

RECIO CUP: BS.

1.500,58

Cm: BS.646,801P 8%: B
MD: BS.539,00 R: BS.0.0D0

DIR: av INTERCOMUNAL MARACAY T

S.77,62

PESO
0.151 KG

GERO EN DESTINO
BS. 2763.99

CANT. CUPONES. 1
TRACKING 012000511000773
ENSACADO PARA (MARACAY)
"""


def test_courier_mrw_por_jerga_cuando_no_sale_la_sigla():
    reader = ShippingLabelReader()
    resultado = reader._parsear(_OCR_MRW_1)
    assert resultado.courier == "mrw"


def test_destinatario_mrw_nombre_desde_dest():
    reader = ShippingLabelReader()
    resultado = reader._parsear(_OCR_MRW_1)
    assert resultado.recipient_name == "WILLIAM AULAR"


def test_destinatario_mrw_telefono_pegado_al_bloque_destino():
    reader = ShippingLabelReader()
    resultado = reader._parsear(_OCR_MRW_1)
    assert resultado.recipient_phone == "04125913710"


def test_direccion_mrw_tras_el_nombre_y_cedula():
    reader = ShippingLabelReader()
    resultado = reader._parsear(_OCR_MRW_1)
    # El OCR mezclo el orden de columnas y partio el texto que sigue a "DIR:";
    # lo que si queda pegado de forma confiable es el resto de la direccion
    # justo despues del nombre+cedula del destinatario.
    assert "TURMERO" in resultado.recipient_address
    assert "ARAGUA" in resultado.recipient_address


def test_resultado_ok_guia_mrw():
    reader = ShippingLabelReader()
    resultado = reader._parsear(_OCR_MRW_1)
    assert resultado.ok is True
    assert resultado.missing_fields == []


# Foto real de una guia de Domesa (formulario impreso, buena calidad). Nombre,
# cedula y telefono vienen juntos separados por comas en una sola linea, y la
# direccion esta bajo 'Localidad:' terminando en 'ZP: NNNN'. Hay DOS 'ZP:' en
# el documento (destino y origen del remitente); hay que agarrar el primero.
_OCR_DOMESA_1 = """Documentos Mercantiles, S.A

MW DOMESA SH GUÍA DE PORTE SERVICIO MASIVO
sl e DDD

Av. Sur 4 con Calle 100 Esquina Puente Soublette, Edif. DOMESA, Parroquia Santa Teresa.
Caracas — Venezuela. Teléfono: 0 501 Domesa 0 (0 501 366372 0). www.domesa.com.ve

R.I.F.: J-00091991-7. CONCESIÓN POSTAL N* 10-09
Origen: ML - 6000

11010 CCS

CARACAS - DISTRITO CAPITAL
Consignación

560000201780
Destino: AA - 1011

22225 PTC |
PUERTO CABELLO - CARABOBO

Destinatario: Alln Vicente Carvajal Castellanos, V-
V13601602, 04244092227

Detalles del Envío
_Peso | Peso Volumétrico
Físico(K9g) | (kg) | Largo(em) |  Atto(cm) | Ancho(em) |
01-08-2026 0,02 o

[e] [e] 0
| recinto | envase | tipodeemase |

Valor Declarado Bs. Protección Plus Bs. Monto Servicio Bs.
0 0 0

Remitente
Erika Alexandra Hernandez Zurilla, V-V24436874, 04142403386

Dirección Localidad: SECTOR S/N, CALLE PLAZA

Destino: ENTRE CALLE BERMUDEZ Y REGENERACI,
Inmueble: C.C. PROFESIONAL PLAZA,
GALERIA PLAZA, NIVEL S/N, LOCAL N*29M-
2, Parroquia: Juan José Flores, Municipio:
Puerto Cabello, Ciudad/Pueblo: Puerto Cabello,
Estado: Carabobo, ZP: 2050

N/A

Punto de
Referencia:

Prueba de Entrega

Remitente:

Dirección Parroquia: Petare, Municipio: Sucre, Ciudad/Pueblo: Caracas, Estado: Distrito
Origen: Capital, ZP: 1073

|
Punto de La California
Referencia:
"""


def test_courier_domesa():
    reader = ShippingLabelReader()
    resultado = reader._parsear(_OCR_DOMESA_1)
    assert resultado.courier == "domesa"


def test_destinatario_domesa_nombre_antes_de_la_primera_coma():
    reader = ShippingLabelReader()
    resultado = reader._parsear(_OCR_DOMESA_1)
    assert resultado.recipient_name == "Alln Vicente Carvajal Castellanos"


def test_destinatario_domesa_telefono():
    reader = ShippingLabelReader()
    resultado = reader._parsear(_OCR_DOMESA_1)
    assert resultado.recipient_phone == "04244092227"


def test_direccion_domesa_agarra_el_zp_del_destino_no_el_del_remitente():
    reader = ShippingLabelReader()
    resultado = reader._parsear(_OCR_DOMESA_1)
    assert "PUERTO CABELLO" in resultado.recipient_address.upper() or "GALERIA PLAZA" in resultado.recipient_address.upper()
    assert "2050" in resultado.recipient_address
    assert "1073" not in resultado.recipient_address


def test_resultado_ok_guia_domesa():
    reader = ShippingLabelReader()
    resultado = reader._parsear(_OCR_DOMESA_1)
    assert resultado.ok is True
    assert resultado.missing_fields == []
