"""
Vectorizacion de imagenes con CLIP (ViT-B/32) para comparacion "smart".

Convierte imagenes en vectores (embeddings) que viven en el mismo espacio, de
modo que dos fotos parecidas tienen vectores cercanos. La similitud se mide con
coseno (0 = nada que ver, 1 = identicas).

El modelo se carga UNA sola vez (es pesado) y se reutiliza. Corre en CPU.
"""
import io
from functools import lru_cache

import httpx
import numpy as np
from PIL import Image
from sentence_transformers import SentenceTransformer

from app.config import Settings


@lru_cache
def _load_model(model_name: str) -> SentenceTransformer:
    """Carga el modelo CLIP una sola vez (cacheado por nombre)."""
    return SentenceTransformer(model_name)


class ImageEmbedder:
    """Genera embeddings de imagenes y calcula similitud entre ellos."""

    def __init__(self, settings: Settings):
        self._model = _load_model(settings.clip_model)

    def embed_bytes(self, data: bytes) -> list[float]:
        """Embedding de una imagen dada como bytes."""
        image = Image.open(io.BytesIO(data)).convert("RGB")
        vector = self._model.encode(image, normalize_embeddings=True)
        return vector.astype(float).tolist()

    def embed_url(self, url: str, timeout: float = 20.0) -> list[float]:
        """Descarga una imagen por URL y devuelve su embedding."""
        resp = httpx.get(url, timeout=timeout, follow_redirects=True)
        resp.raise_for_status()
        return self.embed_bytes(resp.content)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Similitud coseno entre dos vectores ya normalizados (0..1 aprox)."""
    if not a or not b:
        return 0.0
    va, vb = np.array(a), np.array(b)
    denom = np.linalg.norm(va) * np.linalg.norm(vb)
    if denom == 0:
        return 0.0
    return float(np.dot(va, vb) / denom)
