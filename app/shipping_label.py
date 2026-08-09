"""
Lectura de guias de envio (fotos de etiquetas ZOOM/MRW/Domesa) por VLM.

Antes esto usaba Tesseract local (OCR) + un parser por courier a regex.
Se cambio por un modelo de vision (OpenRouter, Qwen3-VL-30B-A3B-Instruct)
que lee la foto con contexto y devuelve directamente courier + datos del
destinatario en JSON. Esto resuelve los casos que rompian el parser viejo:
el logo de MRW es un watermark que Tesseract casi nunca leia, el texto
multicolumna salia mezclado, y letras confundidas (O/0, D/J) rompian los
regex de campo. Un VLM entiende la etiqueta como imagen, no como texto
plano, asi que no necesita heuristicas por courier.

El CLIP (embeddings de imagen) sigue siendo local: eso solo compara si dos
fotos SE PARECEN entre si, no lee texto, y no tiene relacion con esto.

Las etiquetas de mensajeria vienen con calidad de foto variable (angulo,
luz, arrugas de la bolsa) y a veces el texto impreso mismo viene cortado
(ej. un telefono secundario truncado). Por eso esto NUNCA debe usarse a
ciegas para mandarle algo a un cliente real: `LabelReadResult.ok` indica si
se pudieron sacar los 4 campos con confianza razonable; si no, el llamador
debe pedir revision manual en vez de adivinar.

No se confia ciegamente en que el modelo respete el contrato del prompt.
Cada fuente de error conocida tiene su propia defensa en `_parsear` /
`_consultar_vlm`, aunque el prompt ya le pida al modelo que no la cometa:
  - JSON envuelto en fences de markdown pese a pedir "sin markdown".
  - JSON invalido o que no es un objeto.
  - Campos con simbolos que no pertenecen a un nombre/direccion (defecto de
    impresora termica, ver _PROMPT).
  - Telefono con separadores o basura en vez de puros digitos.
  - `courier` con un valor fuera de la lista conocida.
  - Respuesta de OpenRouter sin 'choices' o con contenido vacio.
"""
from __future__ import annotations

import base64
import json
import logging
import re
from dataclasses import dataclass, field
from io import BytesIO

import httpx
from PIL import Image

from app.config import get_settings

logger = logging.getLogger("app.shipping_label")

_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Redes de seguridad ademas del prompt: si igual queda pegado un simbolo raro
# de un defecto de impresora (ver _PROMPT), lo sacamos en vez de dejarlo
# partir la palabra o colarse en el campo.
#
# Nombre: solo letras (con acentos/enie), espacios, guion y apostrofe — lo
# demas no pertenece a un nombre de persona.
_NOMBRE_CARACTERES_VALIDOS_RE = re.compile(r"[^A-Za-zÁÉÍÓÚÑÜáéíóúñü'\-\s]")

# Direccion: mas permisivo que el nombre porque las direcciones venezolanas
# traen numeros, puntuacion y abreviaturas legitimas (ej. "C.C.", "N/D",
# "ZP: 2050", "SECTOR — N/D; PARROQUIA:"). Igual se recorta a un set fijo de
# simbolos conocidos para que un glifo roto no se cuele.
_DIRECCION_CARACTERES_VALIDOS_RE = re.compile(
    r"[^A-Za-z0-9ÁÉÍÓÚÑÜáéíóúñü\s.,;:()'\"/#°º\-–—]"
)

# Telefono: nos quedamos solo con los digitos. El matching en el backend
# (NestJS) ya ignora separadores al comparar, asi que esto no cambia el
# matching, pero evita mostrarle al operador un numero con basura pegada.
_SOLO_DIGITOS_RE = re.compile(r"\D")

# Un telefono venezolano valido tiene 10 u 11 digitos (con o sin el 0
# inicial). Menos que eso es casi seguro un numero truncado/mal leido.
_TELEFONO_MIN_DIGITOS = 10

_COURIERS_VALIDOS = {"zoom", "mrw", "domesa"}

_PROMPT = """Sos un lector de guias de envio venezolanas (couriers ZOOM, MRW o Domesa).

Mira la foto y devolveme SOLO un JSON (sin texto alrededor, sin markdown, sin \
comentarios, sin fences de codigo tipo ```json) con esta forma exacta:
{
  "courier": "zoom" | "mrw" | "domesa" | null,
  "recipient_name": string | null,
  "recipient_phone": string | null,
  "recipient_address": string | null
}

Reglas:
- "courier": identificalo por el logo, formato o jerga propia de cada uno \
(ZOOM, MRW, ENSACADO, CUPONES, DOMESA, GUIA DE PORTE). Si no estas seguro, null.
- "recipient_name": el nombre del DESTINATARIO, nunca el remitente/sender. En \
MRW aparece junto a "DEST:", en Zoom y Domesa junto a "Destinatario:".
- "recipient_phone": telefono venezolano del destinatario en formato \
04XXXXXXXXX (11 digitos, sin espacios ni guiones). Si el numero esta truncado \
o no se lee completo, null.
- "recipient_address": la direccion de ENTREGA del destinatario completa, \
nunca la del remitente/origen.
- Defecto conocido de la impresora termica de ZOOM — aplica por igual a \
"recipient_name" Y "recipient_address", a cualquier texto impreso: las \
vocales acentuadas en mayuscula (Á, É, Í, Ó, Ú) y la Ñ a veces imprimen mal y \
salen como un simbolo roto o un hueco en vez de la letra (ej. "JOS" + \
simbolo raro + " GUALDRON" es casi siempre "JOSÉ GUALDRON"; lo mismo pasa con \
nombres de sector, parroquia o municipio con enie o acento). Cuando veas un \
simbolo que claramente no es una letra pegado entre dos fragmentos de texto, \
no lo transcribas literal: completa la vocal acentuada o enie mas probable \
usando palabras y nombres comunes en Venezuela. Si genuinamente no podes \
inferir que letra falta con confianza razonable, mejor dejala afuera (ej. \
"JOS GUALDRON") a inventar una letra al azar — nunca dejes el simbolo roto \
ni un espacio de mas partiendo la palabra en dos.
- Si no podes leer un campo con confianza razonable (foto borrosa, cortada, \
texto ilegible), poné null en vez de adivinar. Esto se usa para mandarle un \
mensaje a un cliente real: preferible null a un dato incorrecto.
"""


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
    """Lee una foto de guia y extrae courier + datos del destinatario via VLM."""

    def read(self, image: Image.Image) -> LabelReadResult:
        buf = BytesIO()
        image.convert("RGB").save(buf, format="JPEG", quality=90)
        respuesta = self._consultar_vlm(buf.getvalue())
        return self._parsear(respuesta)

    def read_bytes(self, data: bytes) -> LabelReadResult:
        return self.read(Image.open(BytesIO(data)))

    # --- internos: llamada al VLM ---

    def _consultar_vlm(self, jpeg_bytes: bytes) -> str:
        settings = get_settings()
        if not settings.openrouter_api_key:
            raise RuntimeError("OPENROUTER_API_KEY no configurada")

        b64 = base64.b64encode(jpeg_bytes).decode("ascii")
        payload = {
            "model": settings.openrouter_vision_model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": _PROMPT},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                        },
                    ],
                }
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0,
        }
        resp = httpx.post(
            _OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {settings.openrouter_api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=60.0,
        )
        resp.raise_for_status()
        data = resp.json()
        return self._extraer_contenido(data)

    def _extraer_contenido(self, data: dict) -> str:
        """
        No confia en la forma exacta de la respuesta de OpenRouter (rate
        limit devuelto como 200, moderacion de contenido, modelo caido, etc.
        pueden dejar 'choices' vacio o sin 'content'). Si falta algo, se
        levanta un error legible en vez de un KeyError/IndexError crudo.
        """
        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError(f"OpenRouter no devolvio 'choices': {data}")

        contenido = (choices[0].get("message") or {}).get("content")
        if not contenido:
            raise RuntimeError(f"OpenRouter devolvio una respuesta vacia: {data}")

        return contenido

    # --- internos: parseo/validacion de la respuesta ---

    def _parsear(self, respuesta_vlm: str) -> LabelReadResult:
        """
        Valida y normaliza el JSON que devolvio el modelo. No confia en que
        venga bien formado ni en que respete el contrato: si el JSON es
        invalido, viene envuelto en markdown, o falta un campo, se trata
        como no leido (missing_fields), nunca se inventa un valor.
        """
        datos = self._parsear_json(respuesta_vlm)

        courier = str(datos.get("courier") or "").strip().lower()
        if courier not in _COURIERS_VALIDOS:
            courier = ""

        nombre = self._limpiar_nombre(str(datos.get("recipient_name") or ""))
        direccion = self._limpiar_direccion(str(datos.get("recipient_address") or ""))
        telefono = self._limpiar_telefono(str(datos.get("recipient_phone") or ""))

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
            raw_text=respuesta_vlm,
            missing_fields=faltantes,
        )

    def _parsear_json(self, respuesta_vlm: str) -> dict:
        """
        Recorta desde el primer '{' hasta el ultimo '}' antes de parsear, en
        vez de confiar en que el modelo no envuelva el JSON en fences de
        markdown (```json ... ```) o le agregue una frase antes/despues pese
        a que el prompt pida "sin texto alrededor". Si aun asi no es JSON
        valido, se trata como si no hubiera leido nada (todos los campos
        faltantes), nunca se revienta el request.
        """
        inicio = respuesta_vlm.find("{")
        fin = respuesta_vlm.rfind("}")
        bloque = respuesta_vlm[inicio : fin + 1] if inicio != -1 and fin > inicio else respuesta_vlm

        try:
            datos = json.loads(bloque)
            if not isinstance(datos, dict):
                raise ValueError("la respuesta no es un objeto JSON")
            return datos
        except (json.JSONDecodeError, ValueError):
            logger.warning(f"Respuesta del VLM no es JSON valido: {respuesta_vlm[:300]!r}")
            return {}

    def _limpiar_nombre(self, nombre: str) -> str:
        """
        Saca cualquier caracter que no pertenezca a un nombre (ver
        `_NOMBRE_CARACTERES_VALIDOS_RE`). Al haber espacio de sobra alrededor
        del simbolo roto en el texto original ("JOS" + espacio + simbolo +
        espacio + "GUALDRON"), sacarlo y colapsar los espacios deja las
        palabras separadas en vez de pegarlas ("JOS GUALDRON", no
        "JOSGUALDRON").
        """
        limpio = _NOMBRE_CARACTERES_VALIDOS_RE.sub("", nombre)
        return re.sub(r"\s+", " ", limpio).strip()

    def _limpiar_direccion(self, direccion: str) -> str:
        """Mismo criterio que `_limpiar_nombre` pero con el set de simbolos validos de una direccion."""
        limpio = _DIRECCION_CARACTERES_VALIDOS_RE.sub("", direccion)
        return re.sub(r"\s+", " ", limpio).strip()

    def _limpiar_telefono(self, telefono: str) -> str:
        """
        Solo digitos. Si despues de sacar separadores queda muy corto para
        ser un telefono venezolano real, se trata como no leido en vez de
        mandar un numero truncado/basura — el llamador lo va a mostrar tal
        cual en el mensaje de Telegram y usarlo para buscar al comprador.
        """
        limpio = _SOLO_DIGITOS_RE.sub("", telefono)
        if limpio and len(limpio) < _TELEFONO_MIN_DIGITOS:
            return ""
        return limpio
