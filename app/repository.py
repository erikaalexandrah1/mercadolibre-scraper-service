"""
Acceso a datos (MongoDB).

Encapsula la interaccion con Mongo. Dos colecciones:
  - products:   productos scrapeados de la competencia (upsert por link)
  - references: catalogo propio importado de "Mis publicaciones" (upsert por ref_id)
"""
from __future__ import annotations

from pymongo import MongoClient
from pymongo.collection import Collection

from app.config import Settings


class ProductRepository:
    """Repositorio de productos scrapeados en MongoDB."""

    def __init__(self, settings: Settings):
        self._client = MongoClient(settings.mongo_uri, serverSelectionTimeoutMS=5000)
        db = self._client[settings.mongo_db]
        self._products: Collection = db[settings.mongo_collection]
        # Indice unico por link: evita duplicados entre corridas.
        self._products.create_index("link", unique=True)

    def ping(self) -> None:
        """Lanza excepcion si Mongo no responde. Util para /health."""
        self._client.admin.command("ping")

    def save_many(self, products: list[dict]) -> int:
        """Upsert de una lista de productos. Devuelve cuantos se procesaron."""
        for p in products:
            self._products.update_one({"link": p["link"]}, {"$set": p}, upsert=True)
        return len(products)

    def list(
        self,
        query: str | None = None,
        ref_id: str | None = None,
        min_similarity: float | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """Lista productos, con filtros opcionales."""
        filtro: dict = {}
        if query:
            filtro["query"] = query
        if ref_id:
            filtro["ref_id"] = ref_id
        if min_similarity is not None:
            filtro["similarity"] = {"$gte": min_similarity}
        # Cuando se filtra por similitud, ordenar de mas parecido a menos.
        cursor = self._products.find(filtro, {"_id": 0}).limit(limit)
        if min_similarity is not None or ref_id:
            cursor = cursor.sort("similarity", -1)
        return list(cursor)

    def close(self) -> None:
        self._client.close()


class ReferenceRepository:
    """Repositorio del catalogo propio (referencias) en MongoDB."""

    def __init__(self, settings: Settings):
        self._client = MongoClient(settings.mongo_uri, serverSelectionTimeoutMS=5000)
        db = self._client[settings.mongo_db]
        self._references: Collection = db[settings.mongo_references_collection]
        self._references.create_index("ref_id", unique=True)

    def upsert(self, reference: dict) -> None:
        """Inserta o actualiza una referencia por ref_id.

        No pisa 'search_queries' ni 'active' si ya existen (para no perder la
        edicion manual del usuario al re-importar el catalogo).
        """
        existente = self._references.find_one({"ref_id": reference["ref_id"]})
        if existente:
            # Conservar lo editado por el usuario.
            reference.pop("search_queries", None)
            reference.pop("active", None)
        self._references.update_one(
            {"ref_id": reference["ref_id"]}, {"$set": reference}, upsert=True
        )

    def get(self, ref_id: str) -> dict | None:
        return self._references.find_one({"ref_id": ref_id}, {"_id": 0})

    def list(self, only_active: bool = False) -> list[dict]:
        filtro = {"active": True} if only_active else {}
        return list(self._references.find(filtro, {"_id": 0, "embedding": 0}))

    def list_with_embedding(self, only_active: bool = True) -> list[dict]:
        """Como list() pero incluye el embedding (para comparar)."""
        filtro = {"active": True} if only_active else {}
        return list(self._references.find(filtro, {"_id": 0}))

    def update(self, ref_id: str, cambios: dict) -> dict | None:
        """Actualiza campos editables y devuelve la referencia resultante."""
        cambios = {k: v for k, v in cambios.items() if v is not None}
        if cambios:
            self._references.update_one({"ref_id": ref_id}, {"$set": cambios})
        return self.get(ref_id)

    def close(self) -> None:
        self._client.close()
