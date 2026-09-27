from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.exceptions import TelegramBadRequest

from bot.context import AppContext, set_app
from bot.handlers import check as check_mod
from bot.models import ReviewCard
from bot.services.day_progress import DayProgressStore
from bot.services.session import ReviewSession, SessionStore


def _card(cid: str = "c1") -> ReviewCard:
    return ReviewCard(
        card_id=cid,
        answer_type="FAQ",
        answered_at="2026-09-27 12:00:00",
        player_name="P",
        player_id="1",
        question="q",
        admin_name="A",
        answer="a",
    )


@pytest.fixture
def app_ctx(tmp_path):
    sessions = SessionStore(tmp_path / "s.db")
    ctx = AppContext(
        settings=SimpleNamespace(local_sheet_path=tmp_path / "x.csv"),
        panel=SimpleNamespace(used_fixtures=False),
        sheets=None,
        sessions=sessions,
        day_progress=DayProgressStore(tmp_path / "s.db"),
        sheet_backend="none",
    )
    set_app(ctx)
    return ctx


@pytest.mark.asyncio
async def test_set_ui_edits_existing_message(app_ctx) -> None:
    session = ReviewSession(
        chat_id=1,
        day="2026-09-27",
        index=0,
        written=0,
        awaiting_custom=False,
        cards=[_card()],
        recorded_ids=set(),
        ui_message_id=99,
    )
    bot = AsyncMock()
    message = MagicMock()
    message.bot = bot
    message.chat.id = 1

    await check_mod._set_ui(message, session, "hello", reply_markup=None)

    bot.edit_message_text.assert_awaited_once()
    kwargs = bot.edit_message_text.await_args.kwargs
    assert kwargs["message_id"] == 99
    assert kwargs["chat_id"] == 1
    assert kwargs["text"] == "hello"
    bot.send_message.assert_not_awaited()
    loaded = app_ctx.sessions.get(1)
    assert loaded is not None
    assert loaded.ui_message_id == 99


@pytest.mark.asyncio
async def test_set_ui_sends_when_edit_fails(app_ctx) -> None:
    session = ReviewSession(
        chat_id=1,
        day="2026-09-27",
        index=0,
        written=0,
        awaiting_custom=False,
        cards=[_card()],
        recorded_ids=set(),
        ui_message_id=99,
    )
    bot = AsyncMock()
    bot.edit_message_text.side_effect = TelegramBadRequest(
        method=MagicMock(), message="message to edit not found"
    )
    bot.send_message.return_value = SimpleNamespace(message_id=200)
    message = MagicMock()
    message.bot = bot
    message.chat.id = 1

    await check_mod._set_ui(message, session, "hello")

    bot.send_message.assert_awaited_once()
    assert session.ui_message_id == 200
