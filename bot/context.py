from __future__ import annotations

from dataclasses import dataclass

from bot.config import Settings
from bot.services.panel import PanelClient
from bot.services.session import SessionStore
from bot.services.sheets import SheetsClient


@dataclass
class AppContext:
    settings: Settings
    panel: PanelClient
    sheets: SheetsClient | None
    sessions: SessionStore


_CTX: AppContext | None = None


def set_app(ctx: AppContext) -> None:
    global _CTX
    _CTX = ctx


def get_app() -> AppContext:
    if _CTX is None:
        raise RuntimeError("App context is not initialized")
    return _CTX
