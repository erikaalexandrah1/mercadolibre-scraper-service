"""
Tests de la captura de diagnostico en ml_messaging (screenshot + HTML al
fallar el envio por el chat de ML). No usa Playwright real: se le pasa un
objeto Page falso con la misma interfaz que se usa (url, title, screenshot,
content) para no depender de un navegador en el runner de tests.
"""
import base64
from pathlib import Path

import pytest

from app.config import Settings
from app.ml_messaging import MlMessagingError, MlMessagingService

_PNG_FALSO = b"fake-png-bytes"


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

    def screenshot(self, path: str, full_page: bool = True) -> bytes:
        Path(path).write_bytes(_PNG_FALSO)
        return _PNG_FALSO

    def content(self) -> str:
        return self._contenido

    def wait_for_selector(self, selector: str, timeout: int, state: str = "visible"):
        self.ultimo_state_pedido = state
        raise TimeoutError("nunca aparecio")


def _service(tmp_path) -> MlMessagingService:
    settings = Settings(debug_output_dir=str(tmp_path / "debug_output"))
    return MlMessagingService(settings)


# --- _capturar_diagnostico ---


def test_capturar_diagnostico_guarda_screenshot_y_html(tmp_path):
    service = _service(tmp_path)
    page = _PageFalsa(contenido="<div>chat viejo, sin input file</div>")

    diag = service._capturar_diagnostico(page, "selector_no_encontrado_test")

    assert diag.path is not None
    assert Path(f"{diag.path}.png").exists()
    html_path = Path(f"{diag.path}.html")
    assert html_path.exists()
    assert html_path.read_text(encoding="utf-8") == "<div>chat viejo, sin input file</div>"


def test_capturar_diagnostico_devuelve_el_screenshot_en_base64(tmp_path):
    service = _service(tmp_path)

    diag = service._capturar_diagnostico(_PageFalsa(), "test")

    assert diag.screenshot_b64 == base64.b64encode(_PNG_FALSO).decode("ascii")


def test_capturar_diagnostico_nombre_incluye_el_motivo(tmp_path):
    service = _service(tmp_path)

    diag = service._capturar_diagnostico(_PageFalsa(), "boton_enviar_nunca_habilitado")

    assert "boton_enviar_nunca_habilitado" in diag.path


def test_capturar_diagnostico_crea_la_carpeta_si_no_existe(tmp_path):
    service = _service(tmp_path)
    assert not (tmp_path / "debug_output").exists()

    service._capturar_diagnostico(_PageFalsa(), "test")

    assert (tmp_path / "debug_output").exists()


def test_capturar_diagnostico_no_revienta_si_falla_el_screenshot(tmp_path):
    """Si algo en el diagnostico falla, se loguea y se devuelve un _Diagnostico vacio — nunca tapa el error real."""

    class _PageQueRevienta(_PageFalsa):
        def screenshot(self, path: str, full_page: bool = True) -> bytes:
            raise RuntimeError("pagina ya cerrada")

    service = _service(tmp_path)

    diag = service._capturar_diagnostico(_PageQueRevienta(), "test")

    assert diag.path is None
    assert diag.screenshot_b64 is None


# --- el screenshot llega hasta el MlMessagingError que ve el endpoint HTTP ---


def test_esperar_selector_adjunta_el_screenshot_al_error(tmp_path):
    service = _service(tmp_path)

    with pytest.raises(MlMessagingError) as exc_info:
        service._esperar_selector(_PageFalsa(), ".no-existe", "el input de prueba")

    error = exc_info.value
    assert "no se encontro el input de prueba".lower() in str(error).lower()
    assert error.screenshot_b64 == base64.b64encode(_PNG_FALSO).decode("ascii")


# --- state por default vs. el input de archivo, que esta oculto por CSS ---


def test_esperar_selector_usa_visible_por_default(tmp_path):
    """El textarea del chat SI es visible; no tiene sentido relajar esa espera."""
    service = _service(tmp_path)
    page = _PageFalsa()

    with pytest.raises(MlMessagingError):
        service._esperar_selector(page, "textarea", "el campo de texto")

    assert page.ultimo_state_pedido == "visible"


def test_esperar_selector_permite_pedir_attached_para_el_input_de_archivo(tmp_path):
    """
    El <input type=file> del chat de ML esta oculto por CSS (el boton visible
    de 'Adjuntar archivo' es otro elemento); pedir 'visible' ahi nunca
    resuelve, timeoutea siempre. set_input_files funciona igual sobre un
    input oculto, asi que alcanza con 'attached' (en el DOM).
    """
    service = _service(tmp_path)
    page = _PageFalsa()

    with pytest.raises(MlMessagingError):
        service._esperar_selector(page, 'input[type="file"]', "el input de adjuntar", state="attached")

    assert page.ultimo_state_pedido == "attached"
