from __future__ import annotations

import time
from pathlib import Path

from bot.services.panel_session import PanelSessionStore, jwt_seconds_left


def _fake_jwt(exp: int) -> str:
    import base64
    import json

    def enc(obj: dict) -> str:
        raw = json.dumps(obj, separators=(",", ":")).encode()
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    return f"{enc({'alg':'none'})}.{enc({'exp': exp})}.x"


def test_panel_session_roundtrip(tmp_path: Path) -> None:
    store = PanelSessionStore(tmp_path / "panel_session.json")
    token = _fake_jwt(int(time.time()) + 86400)
    store.save(refresh_token=token, access_token=_fake_jwt(int(time.time()) + 3600))
    loaded = store.load()
    assert loaded.refresh_token == token
    assert loaded.access_token
    left = jwt_seconds_left(loaded.refresh_token)
    assert left is not None and left > 0
    assert "refresh" in store.status_text().lower()
