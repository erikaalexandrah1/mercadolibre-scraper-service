"""
Tests de ml_messaging: captura de diagnostico (screenshot + HTML al fallar
el envio por el chat de ML) y desambiguacion por numero de guia cuando el
mismo username matchea mas de una venta. No usa Playwright real: se le pasa
un objeto Page falso con la misma interfaz que se usa, para no depender de
un navegador en el runner de tests.
"""
import base64
from pathlib import Path

import pytest

import app.ml_messaging as ml_messaging
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


# --- desambiguacion por numero de guia cuando el username matchea >1 venta ---


class _TextoFalso:
    def __init__(self, texto: str):
        self._texto = texto

    def inner_text(self) -> str:
        return self._texto


class _HrefFalso:
    def __init__(self, href: str):
        self._href = href

    def get_attribute(self, name: str) -> str:
        return self._href


class _FilaFalsa:
    def __init__(self, nick: str, href: str | None):
        self._nick = nick
        self._href = href

    def query_selector(self, selector: str):
        if selector == ".buyer-nickName":
            return _TextoFalso(self._nick)
        if "a[href" in selector:
            return _HrefFalso(self._href) if self._href else None
        return None


class _PageListado:
    """Simula el listado de ventas + los chats a los que se navega al desambiguar."""

    def __init__(self, filas: list[_FilaFalsa], contenido_por_href: dict[str, str] | None = None):
        self._filas = filas
        self._contenido_por_href = contenido_por_href or {}
        self.hrefs_visitados: list[str] = []

    def query_selector_all(self, selector: str):
        return self._filas if selector == ".sc-row-marketplace" else []

    def goto(self, url: str, wait_until: str | None = None):
        self.hrefs_visitados.append(url)
        if url in self._contenido_por_href and self._contenido_por_href[url] is None:
            raise RuntimeError(f"no se pudo cargar {url}")

    def wait_for_timeout(self, ms: int) -> None:
        pass

    def content(self) -> str:
        return self._contenido_por_href.get(self.hrefs_visitados[-1], "") if self.hrefs_visitados else ""


class _TrackingReaderFalso:
    """Reemplaza a TrackingNumberReader en los tests: no llama a OpenRouter de verdad."""

    def __init__(self, valor: str = "", lanza: bool = False):
        self._valor = valor
        self._lanza = lanza

    def leer(self, image_bytes: bytes) -> str:
        if self._lanza:
            raise RuntimeError("OpenRouter no respondio")
        return self._valor


def test_hrefs_por_username_en_pagina_matchea_case_insensitive_y_sin_duplicados(tmp_path):
    service = _service(tmp_path)
    filas = [
        _FilaFalsa("EddisPadron", "/ventas/nueva/mensajeria/1"),
        _FilaFalsa("otrouser", "/ventas/nueva/mensajeria/2"),
        _FilaFalsa("eddispadron", "/ventas/nueva/mensajeria/1"),  # duplicado
    ]
    page = _PageListado(filas)

    candidatos = service._hrefs_por_username_en_pagina(page, "EDDISPADRON")

    assert candidatos == ["/ventas/nueva/mensajeria/1"]


def test_resolver_href_con_un_solo_candidato_no_necesita_tracking(tmp_path):
    """Sin ambiguedad, _resolver_href retorna antes de siquiera intentar leer el tracking de la foto."""
    service = _service(tmp_path)
    filas = [_FilaFalsa("eddispadron", "/ventas/nueva/mensajeria/1")]
    page = _PageListado(filas)

    href = service._resolver_href(page, "eddispadron", b"foto")

    assert href == "/ventas/nueva/mensajeria/1"


def test_resolver_href_desambigua_por_numero_de_guia_en_un_solo_chat(tmp_path, monkeypatch):
    monkeypatch.setattr(ml_messaging, "TrackingNumberReader", lambda: _TrackingReaderFalso(valor="1695206588"))
    service = _service(tmp_path)
    filas = [
        _FilaFalsa("eddispadron", "/ventas/1"),
        _FilaFalsa("eddispadron", "/ventas/2"),
    ]
    page = _PageListado(
        filas,
        contenido_por_href={
            "/ventas/1": "otros mensajes, sin numero de guia",
            "/ventas/2": "Gracias por tu compra. El número de guía para tu envío es: 1695206588",
        },
    )

    href = service._resolver_href(page, "eddispadron", b"foto")

    assert href == "/ventas/2"


def test_resolver_href_ambiguo_si_el_numero_no_aparece_en_ningun_chat(tmp_path, monkeypatch):
    monkeypatch.setattr(ml_messaging, "TrackingNumberReader", lambda: _TrackingReaderFalso(valor="1695206588"))
    service = _service(tmp_path)
    filas = [
        _FilaFalsa("eddispadron", "/ventas/1"),
        _FilaFalsa("eddispadron", "/ventas/2"),
    ]
    page = _PageListado(
        filas,
        contenido_por_href={
            "/ventas/1": "numero de guia: 0000000000",
            "/ventas/2": "numero de guia: 1111111111",
        },
    )

    with pytest.raises(MlMessagingError, match="ambiguo"):
        service._resolver_href(page, "eddispadron", b"foto")


def test_resolver_href_ambiguo_si_el_numero_aparece_en_mas_de_un_chat(tmp_path, monkeypatch):
    """Si el mismo numero aparece en 2 chats (raro, pero no confiar) sigue sin poder desambiguar solo."""
    monkeypatch.setattr(ml_messaging, "TrackingNumberReader", lambda: _TrackingReaderFalso(valor="1695206588"))
    service = _service(tmp_path)
    filas = [
        _FilaFalsa("eddispadron", "/ventas/1"),
        _FilaFalsa("eddispadron", "/ventas/2"),
    ]
    page = _PageListado(
        filas,
        contenido_por_href={
            "/ventas/1": "numero de guia: 1695206588",
            "/ventas/2": "numero de guia: 1695206588",
        },
    )

    with pytest.raises(MlMessagingError, match="ambiguo"):
        service._resolver_href(page, "eddispadron", b"foto")


def test_resolver_href_nunca_elige_la_mas_nueva_sin_confirmar(tmp_path, monkeypatch):
    """Sin poder leer el numero de guia de la foto, NO se cae a 'la primera de la lista'."""
    monkeypatch.setattr(ml_messaging, "TrackingNumberReader", lambda: _TrackingReaderFalso(lanza=True))
    service = _service(tmp_path)
    filas = [
        _FilaFalsa("eddispadron", "/ventas/1"),
        _FilaFalsa("eddispadron", "/ventas/2"),
    ]
    page = _PageListado(filas)

    with pytest.raises(MlMessagingError, match="no se pudo leer el numero de guia"):
        service._resolver_href(page, "eddispadron", b"foto")


def test_desambiguar_por_tracking_ignora_un_chat_que_no_carga(tmp_path, monkeypatch):
    """Si un candidato falla al navegar, se sigue con los demas en vez de reventar toda la desambiguacion."""
    service = _service(tmp_path)
    page = _PageListado(
        [],
        contenido_por_href={
            "/ventas/1": None,  # goto() va a lanzar para este
            "/ventas/2": "El número de guía para tu envío es: 1695206588",
        },
    )

    href = service._desambiguar_por_tracking(page, "eddispadron", ["/ventas/1", "/ventas/2"], "1695206588")

    assert href == "/ventas/2"
