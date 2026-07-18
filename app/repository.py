"""
Acceso a datos (MongoDB).

Encapsula toda la interaccion con Mongo para que el resto de la app no
dependa directamente de pymongo. Guarda con upsert por 'link' para no duplicar.
"""
from pymongo import MongoClient
from pymongo.collection import Collection

from app.config import Settings


class ProductoRepository:
    """Repositorio de productos en MongoDB."""

    def __init__(self, settings: Settings):
        self._client = MongoClient(settings.mongo_uri, serverSelectionTimeoutMS=5000)
        self._collection: Collection = self._client[settings.mongo_db][settings.mongo_collection]
        # Indice unico por link: evita duplicados entre corridas.
        self._collection.create_index("link", unique=True)

    def ping(self) -> None:
        """Lanza excepcion si Mongo no responde. Util para /health."""
        self._client.admin.command("ping")

    def guardar_muchos(self, productos: list[dict]) -> int:
        """Upsert de una lista de productos. Devuelve cuantos se procesaron."""
        for p in productos:
            self._collection.update_one({"link": p["link"]}, {"$set": p}, upsert=True)
        return len(productos)

    def listar(self, consulta: str | None = None, limite: int = 50) -> list[dict]:
        """Lista productos guardados, opcionalmente filtrando por consulta."""
        filtro = {"consulta": consulta} if consulta else {}
        cursor = self._collection.find(filtro, {"_id": 0}).limit(limite)
        return list(cursor)

    def close(self) -> None:
        self._client.close()
