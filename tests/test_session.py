from __future__ import annotations

from pathlib import Path

from bot.models import ReviewCard
from bot.services.session import ReviewSession, SessionStore


def test_session_roundtrip(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "sessions.db")
    card = ReviewCard(
        card_id="abc",
        answer_type="FAQ",
        answered_at="2026-09-27 12:00:00",
        player_name="Player",
        player_id="1",
        question="q",
        admin_name="Admin",
        answer="a",
    )
    session = ReviewSession(
        chat_id=42,
        day="2026-09-27",
        index=1,
        written=1,
        awaiting_custom=True,
        cards=[card],
        recorded_ids={"abc"},
        ui_message_id=777,
    )
    store.save(session)
    loaded = store.get(42)
    assert loaded is not None
    assert loaded.index == 1
    assert loaded.awaiting_custom is True
    assert loaded.recorded_ids == {"abc"}
    assert loaded.ui_message_id == 777
    assert loaded.cards[0].admin_name == "Admin"
    store.clear(42)
    assert store.get(42) is None
