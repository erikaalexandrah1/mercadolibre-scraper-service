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
debe pedir revision manual en vez de adivinar. El prompt le pide al modelo
explicitamente que devuelva null en vez de adivinar un campo que no puede
leer con confianza.
"""
from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass, field
from io import BytesIO

import httpx
from PIL import Image

from app.config import get_settings

logger = logging.getLogger("app.shipping_label")

_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

_COURIERS_VALIDOS = {"zoom", "mrw", "domesa"}

_PROMPT = """Sos un lector de guias de envio venezolanas (couriers ZOOM, MRW o Domesa).

Mira la foto y devolveme SOLO un JSON (sin texto alrededor, sin markdown, sin \
comentarios) con esta forma exacta:
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

    # --- internos ---

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
        return data["choices"][0]["message"]["content"]

    def _parsear(self, respuesta_vlm: str) -> LabelReadResult:
        """
        Valida y normaliza el JSON que devolvio el modelo. No confia en que
        venga bien formado ni en que respete el contrato: si el JSON es
        invalido o falta un campo, se trata como no leido (missing_fields),
        nunca se inventa un valor.
        """
        try:
            datos = json.loads(respuesta_vlm)
            if not isinstance(datos, dict):
                raise ValueError("la respuesta no es un objeto JSON")
        except (json.JSONDecodeError, ValueError):
            logger.warning(f"Respuesta del VLM no es JSON valido: {respuesta_vlm[:300]!r}")
            datos = {}

        courier = str(datos.get("courier") or "").strip().lower()
        if courier not in _COURIERS_VALIDOS:
            courier = ""

        nombre = str(datos.get("recipient_name") or "").strip()
        telefono = str(datos.get("recipient_phone") or "").strip()
        direccion = str(datos.get("recipient_address") or "").strip()

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
