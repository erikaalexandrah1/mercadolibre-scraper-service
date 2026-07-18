"""
Tests unitarios de la logica pura (sin red ni navegador).

Se centran en el parseo, que es la parte fragil y facil de romper cuando
MercadoLibre cambia sus textos.
"""
from app.scraper import _parsear_cantidad_vendida


def test_cantidad_con_prefijo_mas():
    assert _parsear_cantidad_vendida("Nuevo  |  +5 vendidos") == 5


def test_cantidad_con_miles():
    assert _parsear_cantidad_vendida("Nuevo | +1.200 vendidos") == 1200


def test_cantidad_simple():
    assert _parsear_cantidad_vendida("10 vendidos") == 10


def test_sin_cantidad():
    assert _parsear_cantidad_vendida("Nuevo") == 0
    assert _parsear_cantidad_vendida("") == 0
