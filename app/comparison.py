"""
Comparacion por imagen: catalogo propio vs competencia.

Por cada referencia activa:
  1. Busca competencia con sus 'search_queries' (los tags editables).
  2. Vectoriza la foto de cada producto encontrado.
  3. Calcula la similitud (coseno) contra el embedding de la referencia.
  4. Guarda cada producto con su 'ref_id' y 'similarity'.
"""
from app.config import Settings
from app.embeddings import ImageEmbedder, cosine_similarity
from app.scraper import MercadoLibreScraper


class ComparisonService:
    """Compara referencias del catalogo contra productos de la competencia."""

    def __init__(self, settings: Settings, embedder: ImageEmbedder):
        self._settings = settings
        self._embedder = embedder
        self._scraper = MercadoLibreScraper(settings)

    def compare_reference(self, reference: dict, pages: int, max_items: int) -> list[dict]:
        """
        Devuelve los productos de competencia de una referencia, cada uno con
        'ref_id' y 'similarity'. 'reference' debe incluir su 'embedding'.
        """
        ref_embedding = reference.get("embedding") or []
        productos: dict[str, dict] = {}  # link -> producto (dedupe entre queries)

        for query in reference.get("search_queries", []):
            for prod in self._scraper.run(query=query, pages=pages, max_items=max_items):
                productos.setdefault(prod["link"], prod)

        resultado: list[dict] = []
        for prod in productos.values():
            similarity = 0.0
            if ref_embedding and prod.get("image_url"):
                try:
                    prod_emb = self._embedder.embed_url(prod["image_url"])
                    similarity = cosine_similarity(ref_embedding, prod_emb)
                except Exception:
                    similarity = 0.0
            prod["ref_id"] = reference["ref_id"]
            prod["similarity"] = round(similarity, 4)
            resultado.append(prod)
        return resultado
