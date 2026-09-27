from __future__ import annotations

import base64
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class PanelTokenBundle:
    refresh_token: str = ""
    access_token: str = ""
    updated_at: float = 0.0


def _b64url_json(segment: str) -> dict:
    padded = segment + "=" * (-len(segment) % 4)
    raw = base64.urlsafe_b64decode(padded.encode("ascii"))
    return json.loads(raw.decode("utf-8"))


def jwt_exp(token: str) -> int | None:
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return None
        payload = _b64url_json(parts[1])
        exp = payload.get("exp")
        return int(exp) if exp is not None else None
    except Exception:  # noqa: BLE001
        return None


def jwt_seconds_left(token: str, *, now: float | None = None) -> float | None:
    exp = jwt_exp(token)
    if exp is None:
        return None
    return exp - (now if now is not None else time.time())


class PanelSessionStore:
    """Persist panel cookies so restarts do not require editing .env."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> PanelTokenBundle:
        if not self.path.is_file():
            return PanelTokenBundle()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            logger.exception("Failed to read panel session file %s", self.path)
            return PanelTokenBundle()
        return PanelTokenBundle(
            refresh_token=str(data.get("refresh_token") or "").strip(),
            access_token=str(data.get("access_token") or "").strip(),
            updated_at=float(data.get("updated_at") or 0),
        )

    def save(self, *, refresh_token: str, access_token: str = "") -> None:
        bundle = PanelTokenBundle(
            refresh_token=refresh_token.strip(),
            access_token=access_token.strip(),
            updated_at=time.time(),
        )
        tmp = self.path.with_suffix(".tmp")
        payload = {
            "refresh_token": bundle.refresh_token,
            "access_token": bundle.access_token,
            "updated_at": bundle.updated_at,
            "refresh_exp": jwt_exp(bundle.refresh_token),
            "access_exp": jwt_exp(bundle.access_token),
        }
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)
        try:
            self.path.chmod(0o600)
        except OSError:
            pass
        logger.info(
            "Saved panel session to %s (refresh_left=%ss)",
            self.path,
            jwt_seconds_left(bundle.refresh_token),
        )

    def status_text(self, bundle: PanelTokenBundle | None = None) -> str:
        bundle = bundle or self.load()
        if not bundle.refresh_token:
            return "Сессия панели: нет refresh_token"
        refresh_left = jwt_seconds_left(bundle.refresh_token)
        access_left = (
            jwt_seconds_left(bundle.access_token) if bundle.access_token else None
        )
        lines = ["Сессия панели:"]
        if refresh_left is None:
            lines.append("• refresh: есть (срок неизвестен)")
        else:
            days = refresh_left / 86400
            lines.append(f"• refresh: ещё ~{days:.1f} дн.")
        if access_left is None:
            lines.append("• access: будет обновлён автоматически")
        else:
            hours = access_left / 3600
            lines.append(f"• access: ещё ~{hours:.1f} ч. (обновляется сам)")
        lines.append("Файл: data/panel_session.json")
        return "\n".join(lines)
