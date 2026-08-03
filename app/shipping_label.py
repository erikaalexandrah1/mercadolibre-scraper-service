"""
Lectura de guias de envio (fotos de etiquetas ZOOM/MRW/Domesa) por OCR local.

No usa CLIP ni ningun servicio externo: el embedder de imagenes (CLIP) solo
compara si dos fotos SE PARECEN entre si, no lee texto. Para leer courier,
destinatario, telefono y direccion de la etiqueta impresa se usa Tesseract
(local, gratis) con un preprocesamiento simple (escala de grises + upscale
2x) que en las pruebas fue el que mejor resultado dio contra fotos reales
sacadas con celular.

Las etiquetas de mensajeria vienen con calidad de foto variable (angulo,
luz, arrugas de la bolsa) y a veces el texto impreso mismo viene cortado
(ej. un telefono secundario truncado). Por eso esto NUNCA debe usarse a
ciegas para mandarle algo a un cliente real: `LabelReadResult.ok` indica si
se pudieron sacar los 3 campos con confianza razonable; si no, el llamador
debe pedir revision manual en vez de adivinar.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import pytesseract
from PIL import Image

# Telefono venezolano tipico: 04XX-XXXXXXX (con o sin separadores).
_TELEFONO_RE = re.compile(r"0\d{3}[\s.\-]?\d{3}[\s.\-]?\d{2}[\s.\-]?\d{2}")

# Etiqueta 'DEST:' de MRW: la D inicial sale confundida seguido (ej. 'pesT:'),
# por eso se tolera cualquier letra + 'es' + T/L. El ':' es obligatorio para
# no matchear por accidente dentro de 'DESTINO:' (el bloque de la oficina de
# entrega, que es OTRO campo).
_MRW_DEST_LABEL = r"[A-Za-z]es[TtLl]:"

_COURIER_PATTERNS: dict[str, re.Pattern] = {
    # 'ZOOM' sale seguido como 'Z00M', '¿00M' o incluso '200M' en el OCR
    # (confunde O con 0, y la Z con ¿, ? o 2 segun la foto).
    "zoom": re.compile(r"[Z2¿?][O0]{2}M", re.IGNORECASE),
    # El logo 'MRW' de la bolsa es un watermark diagonal, no texto plano: el
    # OCR casi nunca lo lee. Se reconoce por jerga propia de su formato de
    # guia en vez de depender de la sigla.
    "mrw": re.compile(r"\bMRW\b|ENSACADO|CUPONES|COBRO EN DESTINO", re.IGNORECASE),
    "domesa": re.compile(r"DOMESA", re.IGNORECASE),
}


@dataclass
class LabelReadResult:
    """Resultado de leer una guia. `ok` es False si falta algun campo clave."""

    courier: str = ""  # 'zoom' | 'mrw' | 'domesa' | '' (no reconocido)
    recipient_name: str = ""
    recipient_phone: str = ""
    recipient_address: str = ""
    raw_text: str = ""
    missing_fields: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.missing_fields


class ShippingLabelReader:
    """Lee una foto de guia y extrae courier + datos del destinatario."""

    def read(self, image: Image.Image) -> LabelReadResult:
        texto = self._ocr(image)
        return self._parsear(texto)

    def read_bytes(self, data: bytes) -> LabelReadResult:
        from io import BytesIO

        return self.read(Image.open(BytesIO(data)))

    # --- internos ---

    def _ocr(self, image: Image.Image) -> str:
        """Escala de grises + upscale 2x + PSM 3: lo que mejor funcionó en pruebas."""
        gris = image.convert("L")
        ancho, alto = gris.size
        agrandada = gris.resize((ancho * 2, alto * 2), Image.LANCZOS)
        return pytesseract.image_to_string(agrandada, lang="spa", config="--psm 3")

    def _parsear(self, texto: str) -> LabelReadResult:
        courier = self._extraer_courier(texto)
        if courier == "mrw":
            nombre, telefono = self._extraer_destinatario_mrw(texto)
            direccion = self._extraer_destino_mrw(texto)
        else:
            nombre, telefono = self._extraer_destinatario(texto)
            direccion = self._extraer_destino(texto)

        faltantes = []
        if not courier:
            faltantes.append("courier")
        if not nombre:
            faltantes.append("recipient_name")
        if not telefono:
            faltantes.append("recipient_phone")
        if not direccion:
            faltantes.append("recipient_address")

        return LabelReadResult(
            courier=courier,
            recipient_name=nombre,
            recipient_phone=telefono,
            recipient_address=direccion,
            raw_text=texto,
            missing_fields=faltantes,
        )

    def _extraer_courier(self, texto: str) -> str:
        for courier, patron in _COURIER_PATTERNS.items():
            if patron.search(texto):
                return courier
        return ""

    def _extraer_destinatario(self, texto: str) -> tuple[str, str]:
        """
        De 'Destinatario:EDDIS ENRIQUE PADRON COLINA(Tel.04121623093/4' saca
        ('EDDIS ENRIQUE PADRON COLINA', '04121623093').

        La 'D' inicial a veces sale como 'J' en el OCR (confusion de fuente),
        por eso se matchea cualquier letra + 'estinatario'. El telefono en la
        etiqueta a veces viene truncado a mitad (segundo numero incompleto);
        nos quedamos con el primer telefono valido.
        """
        m = re.search(
            r"[A-Za-z]es[tl]inatario:?\s*([A-ZÁÉÍÓÚÑa-záéíóúñ][A-Za-zÁÉÍÓÚÑáéíóúñ .]+?)\s*\(?\s*[Tt]el[.,]?\s*([\d /]+)",
            texto,
            re.IGNORECASE,
        )
        if not m:
            return "", ""

        nombre = re.sub(r"\s+", " ", m.group(1)).strip()
        telefonos = _TELEFONO_RE.findall(m.group(2))
        telefono = telefonos[0] if telefonos else ""
        return nombre, telefono

    def _extraer_destinatario_mrw(self, texto: str) -> tuple[str, str]:
        """
        MRW usa un formato de campos distinto al de Zoom/Domesa: el nombre
        viene en 'DEST: WILLIAM AULAR V-11820181' (nombre + cedula, sin
        telefono ahi), y el telefono del destinatario esta pegado al bloque
        anterior de 'DESTINO:' (la oficina/direccion de entrega), no al
        nombre. El TLF que aparece ANTES de 'DESTINO:' es el del remitente,
        no nos sirve.
        """
        m_nombre = re.search(
            _MRW_DEST_LABEL + r"\s*([A-ZÁÉÍÓÚÑa-záéíóúñ][A-Za-zÁÉÍÓÚÑáéíóúñ .]+?)\s*[VEve][-.]?\d{6,9}",
            texto,
            re.IGNORECASE,
        )
        nombre = re.sub(r"\s+", " ", m_nombre.group(1)).strip() if m_nombre else ""

        telefono = ""
        m_bloque = re.search(r"DESTINO:(.+?)" + _MRW_DEST_LABEL, texto, re.DOTALL | re.IGNORECASE)
        if m_bloque:
            telefonos = _TELEFONO_RE.findall(m_bloque.group(1))
            telefono = telefonos[0] if telefonos else ""

        return nombre, telefono

    def _extraer_destino_mrw(self, texto: str) -> str:
        """
        OJO: en la foto de prueba, Tesseract mezclo el orden de lectura entre
        columnas (multi-columna con precios al lado) y el texto que sigue a
        'DIR:' quedo partido/incompleto. Lo que SI queda pegado de forma
        confiable es el resto de la direccion justo despues del nombre+cedula
        (' DEST: NOMBRE V-12345678'), asi que se ancla ahi en vez de en 'DIR:'.
        Termina en el codigo postal ('CP ...') o en la seccion de tipo de
        envio ('TIPO:').
        """
        m_dest = re.search(
            _MRW_DEST_LABEL + r"\s*[A-ZÁÉÍÓÚÑa-záéíóúñ][A-Za-zÁÉÍÓÚÑáéíóúñ .]+?\s*[VEve][-.]?\d{6,9}",
            texto,
            re.IGNORECASE,
        )
        resto = texto[m_dest.end():] if m_dest else texto

        m = re.search(r"(.+?)(?:\bCP\b|TIPO)", resto, re.DOTALL | re.IGNORECASE)
        if not m:
            m = re.search(r"(.+?)(?:\n\s*\n|\Z)", resto, re.DOTALL)
        if not m:
            return ""
        direccion = re.sub(r"\s*\n\s*", " ", m.group(1))
        return re.sub(r"\s+", " ", direccion).strip()

    def _extraer_destino(self, texto: str) -> str:
        """
        Todo lo que sigue a 'Destino:' (con la misma confusion D/J que el
        destinatario). El bloque de direccion termina siempre en 'ZONA
        POSTAL', asi que se usa como marcador de fin en vez de cortar en el
        primer salto de linea (la impresora corta a mitad de palabra al
        pasar de linea, ej. 'PARR' + 'OQUIA', asi que un salto de linea NO
        implica que la direccion termino ahi).
        """
        m = re.search(r"[A-Za-z]?es[tl]ino:?\s*(.+?)ZONA\s*POSTA", texto, re.DOTALL | re.IGNORECASE)
        if not m:
            # Sin el marcador de fin: mejor esfuerzo hasta el primer parrafo en blanco.
            m = re.search(r"[A-Za-z]?es[tl]ino:?\s*(.+?)(?:\n\s*\n|\Z)", texto, re.DOTALL | re.IGNORECASE)
        if not m:
            return ""
        direccion = re.sub(r"\s*\n\s*", " ", m.group(1))
        return re.sub(r"\s+", " ", direccion).strip()
