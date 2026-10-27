"""Browser tests: a real Chromium against the live FastAPI app and against the static demo."""

from __future__ import annotations

import functools
import http.server
import socket
import threading
from pathlib import Path

import pytest

pytest.importorskip("playwright")
from playwright.sync_api import sync_playwright  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def pytest_collection_modifyitems(items):
    for item in items:
        if "e2e" in str(item.fspath):
            item.add_marker(pytest.mark.e2e)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def api_url():
    import uvicorn

    from whyitmatters.api import create_app

    port = _free_port()
    config = uvicorn.Config(create_app(), host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        thread.join(0.05)
    yield f"http://127.0.0.1:{port}/"
    server.should_exit = True
    thread.join(5)


@pytest.fixture(scope="session")
def static_url():
    directory = str(ROOT / "dist" / "demo")
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=directory)
    handler.log_message = lambda *a, **k: None
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}/"
    srv.shutdown()


@pytest.fixture(scope="session")
def browser():
    with sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception:  # noqa: BLE001  (no bundled Chromium locally: use an installed Chrome)
            b = p.chromium.launch(channel="chrome")
        yield b
        b.close()


@pytest.fixture
def new_page(browser):
    """A page factory that records every uncaught page error; the test asserts there were none."""
    pages, errors = [], []

    def make(**kw):
        ctx = browser.new_context(**kw)
        page = ctx.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        pages.append(ctx)
        return page

    yield make
    for ctx in pages:
        ctx.close()
    assert errors == [], f"page errors: {errors}"
