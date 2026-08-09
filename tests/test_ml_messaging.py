"""
Tests de la captura de diagnostico en ml_messaging (screenshot + HTML al
fallar el envio por el chat de ML). No usa Playwright real: se le pasa un
objeto Page falso con la misma interfaz que se usa (url, title, screenshot,
content) para no depender de un navegador en el runner de tests.
"""
from pathlib import Path

from app.config import Settings
from app.ml_messaging import MlMessagingService


class _PageFalsa:
    def __init__(
        self,
        url: str = "https://www.mercadolibre.com.ve/ventas/nueva/mensajeria/123",
        title: str = "Mensajes",
        contenido: str = "<html></html>",
    ):
        self.url = url
        self._title = title
        self._contenido = contenido

    def title(self) -> str:
        return self._title

    def screenshot(self, path: str, full_page: bool = True) -> None:
        Path(path).write_bytes(b"fake-png-bytes")

    def content(self) -> str:
        return self._contenido


def _service(tmp_path) -> MlMessagingService:
    settings = Settings(debug_output_dir=str(tmp_path / "debug_output"))
    return MlMessagingService(settings)


def test_capturar_diagnostico_guarda_screenshot_y_html(tmp_path):
    service = _service(tmp_path)
    page = _PageFalsa(contenido="<div>chat viejo, sin input file</div>")

    ruta = service._capturar_diagnostico(page, "selector_no_encontrado_test")

    assert ruta is not None
    assert Path(f"{ruta}.png").exists()
    html_path = Path(f"{ruta}.html")
    assert html_path.exists()
    assert html_path.read_text(encoding="utf-8") == "<div>chat viejo, sin input file</div>"


def test_capturar_diagnostico_nombre_incluye_el_motivo(tmp_path):
    service = _service(tmp_path)

    ruta = service._capturar_diagnostico(_PageFalsa(), "boton_enviar_nunca_habilitado")

    assert "boton_enviar_nunca_habilitado" in ruta


def test_capturar_diagnostico_crea_la_carpeta_si_no_existe(tmp_path):
    service = _service(tmp_path)
    assert not (tmp_path / "debug_output").exists()

    service._capturar_diagnostico(_PageFalsa(), "test")

    assert (tmp_path / "debug_output").exists()


def test_capturar_diagnostico_no_revienta_si_falla_el_screenshot(tmp_path):
    """Si algo en el diagnostico falla, se loguea y se devuelve None — nunca tapa el error real."""

    class _PageQueRevienta(_PageFalsa):
        def screenshot(self, path: str, full_page: bool = True) -> None:
            raise RuntimeError("pagina ya cerrada")

    service = _service(tmp_path)

    ruta = service._capturar_diagnostico(_PageQueRevienta(), "test")

    assert ruta is None
