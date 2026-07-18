"""Tests de la logica pura de imagen/catalogo (sin red ni modelo)."""
from app.catalog import _url_articulo
from app.embeddings import cosine_similarity


def test_cosine_identicos():
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == 1.0


def test_cosine_ortogonales():
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0


def test_cosine_vacio():
    assert cosine_similarity([], [1.0, 2.0]) == 0.0


def test_url_articulo():
    assert _url_articulo("MLV560637663") == (
        "https://articulo.mercadolibre.com.ve/MLV-560637663-_JM"
    )
