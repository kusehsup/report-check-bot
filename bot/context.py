from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from bot.config import Settings
from bot.models import ReviewCard
from bot.services.panel import PanelClient
from bot.services.session import SessionStore


class SheetStore(Protocol):
    def filter_new_cards(self, cards: list[ReviewCard]) -> list[ReviewCard]: ...

    def append_verdict(self, card: ReviewCard, verdict: str) -> None: ...


@dataclass
class AppContext:
    settings: Settings
    panel: PanelClient
    sheets: SheetStore | None
    sessions: SessionStore
    sheet_backend: str = "none"


_CTX: AppContext | None = None


def set_app(ctx: AppContext) -> None:
    global _CTX
    _CTX = ctx


def get_app() -> AppContext:
    if _CTX is None:
        raise RuntimeError("App context is not initialized")
    return _CTX
