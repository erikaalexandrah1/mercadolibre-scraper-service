"""
Configuracion del servicio.

Todos los valores se leen de variables de entorno (12-factor app), con
valores por defecto sensatos para desarrollo local. En produccion (Coolify)
se inyectan como variables de entorno del contenedor.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

# User-agent realista. Sin esto, MercadoLibre detecta el navegador automatizado
# y responde con una pagina de error en lugar de los resultados.
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


class Settings(BaseSettings):
    """Configuracion tipada del servicio, cargada desde el entorno / .env."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- MongoDB ---
    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db: str = "mercadolibre"
    mongo_collection: str = "productos"

    # --- Playwright / scraping ---
    # Ruta al archivo de sesion generado con scripts/login.py.
    storage_state_path: str = "storage_state.json"
    headless: bool = True
    user_agent: str = DEFAULT_USER_AGENT
    # Timeout por navegacion, en milisegundos.
    nav_timeout_ms: int = 30000

    # --- API ---
    # Si se define, todas las rutas (excepto /health) exigen el header
    # 'X-API-Key' con este valor. Si queda vacio, la API es abierta.
    api_key: str = ""

    @property
    def auth_enabled(self) -> bool:
        return bool(self.api_key)


@lru_cache
def get_settings() -> Settings:
    """Devuelve la configuracion como singleton (se cachea)."""
    return Settings()
