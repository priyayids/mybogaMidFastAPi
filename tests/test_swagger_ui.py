import re

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_swagger_ui_loads_standalone_preset_script():
    """The standalone preset ships as a separate file and must be loaded.

    Without it SwaggerUIStandalonePreset is undefined at runtime and the
    Authorize button never renders, so X-Client-API-Key cannot be attached
    to "Try it out" requests.
    """
    html = client.get("/docs").text
    assert "/static/swagger-ui-standalone-preset.js" in html


def test_swagger_ui_uses_bare_global_standalone_preset():
    """Reference the standalone preset as a bare global object.

    swagger-ui-standalone-preset.js assigns a global SwaggerUIStandalonePreset
    that is ALREADY the resolved preset (its factory runs at definition time).
    FastAPI's default template references it as
    SwaggerUIBundle.SwaggerUIStandalonePreset, which is undefined on that
    object and throws at page load, leaving the Authorize button unrendered.
    """
    html = client.get("/docs").text
    assert re.search(
        r"presets:\s*\[[^\]]*?SwaggerUIStandalonePreset\s*[\],]", html, re.S
    ), "standalone preset not present in the presets array"
    assert "SwaggerUIBundle.SwaggerUIStandalonePreset" not in html
    # It is an object, not a factory: calling it throws in the browser.
    assert "SwaggerUIStandalonePreset()" not in html


def test_standalone_preset_asset_ships_in_static():
    """The JS asset itself must exist, otherwise the script tag 404s."""
    from pathlib import Path

    asset = Path(__file__).resolve().parents[1] / "app" / "static" / "swagger-ui-standalone-preset.js"
    assert asset.is_file(), f"missing {asset.name}"
    assert "SwaggerUIStandalonePreset" in asset.read_text(encoding="utf-8")


def test_openapi_declares_api_key_security_scheme():
    """The Authorize dialog only offers schemes the spec declares."""
    spec = client.get("/openapi.json").json()
    schemes = spec["components"]["securitySchemes"]
    assert schemes["APIKeyHeader"]["name"] == "X-Client-API-Key"
    assert schemes["APIKeyHeader"]["in"] == "header"

    # Protected operations must actually require it.
    for path, ops in spec["paths"].items():
        for method, op in ops.items():
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            if path == "/" or path.endswith("/healthz"):
                continue  # public health probes
            if "nuveq/{secret_token}" in path:
                continue  # inbound: authenticated by URL secret instead
            assert op.get("security"), f"{method.upper()} {path} is unprotected in the spec"
