from __future__ import annotations

import json
import urllib.error
import urllib.request

import pytest

from overload.ui.web.server import create_web_server


def _http_json(base: str, method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        f"{base}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


@pytest.fixture
def web_app(tmp_path):
    srv = create_web_server(
        destination_dir=tmp_path / "downloads",
        db_path=tmp_path / "library.db",
        host="127.0.0.1",
        port=0,
        demo_lab=True,
    )
    srv.enable_os_open = False
    srv.start_background()
    yield srv
    srv.manager.shutdown()
    srv.history.close()
    srv.shutdown()


def test_web_ui_state_settings_batch_and_folder_inspector(web_app):
    base = web_app.url
    with urllib.request.urlopen(f"{base}/", timeout=5) as home:
        assert home.status == 200
        assert "OverLoad" in home.read().decode("utf-8")

    code, state = _http_json(base, "GET", "/api/state")
    assert code == 200
    assert state["demo"]["enabled"] is True

    # Mise à jour dynamique des limites
    code, updated = _http_json(
        base,
        "POST",
        "/api/settings",
        {"max_concurrent": 4, "speed_limit_bps": 2 * 1024 * 1024},
    )
    assert code == 200
    assert updated["settings"]["max_concurrent"] == 4
    assert updated["settings"]["speed_limit_bps"] == 2 * 1024 * 1024

    # Lancement d'un téléchargement et vérification de l'ouverture du dossier + conflit doublon
    single_url = state["demo"]["single_url"]
    code, created = _http_json(base, "POST", "/api/downloads", {"url": single_url})
    assert code == 201
    assert web_app.manager.wait_all(timeout=15)

    code_dup, dup_resp = _http_json(base, "POST", "/api/downloads", {"url": single_url})
    assert code_dup == 409
    assert dup_resp["conflict"] is True

    code_dir, folder_info = _http_json(
        base, "POST", "/api/open-folder", {"task_id": created["task"]["id"]}
    )
    assert code_dir == 200
    assert any(f["highlighted"] for f in folder_info["entries"])

    # Même avec le banc d'essai activé, les autres adresses privées restent refusées
    code_priv, priv_resp = _http_json(
        base, "POST", "/api/downloads", {"url": "http://192.168.1.10/secret.bin"}
    )
    assert code_priv == 400
    assert "privée" in priv_resp["error"] or "privée" in priv_resp["cause"]
