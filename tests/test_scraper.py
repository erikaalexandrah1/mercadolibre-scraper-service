"""
Tests unitarios de la logica pura (sin red ni navegador).

Se centran en el parseo, que es la parte fragil y facil de romper cuando
MercadoLibre cambia sus textos.
"""
from app.scraper import _limpiar_vendedor, _parsear_cantidad_vendida, _sin_duplicados


def test_cantidad_con_prefijo_mas():
    assert _parsear_cantidad_vendida("Nuevo  |  +5 vendidos") == 5


def test_cantidad_con_miles():
    assert _parsear_cantidad_vendida("Nuevo | +1.200 vendidos") == 1200


def test_cantidad_simple():
    assert _parsear_cantidad_vendida("10 vendidos") == 10


def test_sin_cantidad():
    assert _parsear_cantidad_vendida("Nuevo") == 0
    assert _parsear_cantidad_vendida("") == 0


def test_vendedor_no_oficial_quita_prefijo():
    assert _limpiar_vendedor("Vendido por INNOVTRONIKS") == "INNOVTRONIKS"


def test_vendedor_oficial_sin_prefijo():
    assert _limpiar_vendedor("Nuovocell") == "Nuovocell"


def test_sin_duplicados_conserva_orden():
    assert _sin_duplicados(["a", "b", "a", "c", "b"]) == ["a", "b", "c"]
