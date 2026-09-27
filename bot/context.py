from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from bot.config import Settings
from bot.models import ReviewCard
from bot.services.day_progress import DayProgressStore
from bot.services.panel import PanelClient
from bot.services.reviewed import ReviewedStore
from bot.services.session import SessionStore
from bot.services.skip_rules import SkipRulesStore


class SheetStore(Protocol):
    def filter_new_cards(self, cards: list[ReviewCard]) -> list[ReviewCard]: ...

    def append_verdict(self, card: ReviewCard, verdict: str) -> None: ...

    def written_counts_by_date(self) -> dict[str, int]: ...


@dataclass
class AppContext:
    settings: Settings
    panel: PanelClient
    sheets: SheetStore | None
    sessions: SessionStore
    day_progress: DayProgressStore
    skip_rules: SkipRulesStore
    reviewed: ReviewedStore
    sheet_backend: str = "none"


_CTX: AppContext | None = None


def set_app(ctx: AppContext) -> None:
    global _CTX
    _CTX = ctx


def get_app() -> AppContext:
    if _CTX is None:
        raise RuntimeError("App context is not initialized")
    return _CTX
