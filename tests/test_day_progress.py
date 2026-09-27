from __future__ import annotations

from pathlib import Path

from bot.keyboards import day_picker
from bot.services.day_progress import DayProgress, DayProgressStore
from bot.services.local_sheet import LocalSheetStore
from bot.services.panel import moscow_recent_days
from bot.models import ReviewCard


def test_day_progress_roundtrip(tmp_path: Path) -> None:
    store = DayProgressStore(tmp_path / "p.db")
    store.save_load("2026-09-27", total=100, remaining=12)
    got = store.get("2026-09-27")
    assert got is not None
    assert got.last_total == 100
    assert got.last_remaining == 12
    assert got.force_reload is False

    store.set_remaining("2026-09-27", 5)
    assert store.get("2026-09-27").last_remaining == 5

    store.mark_force_reload("2026-09-27")
    assert store.get("2026-09-27").force_reload is True
    store.save_load("2026-09-27", total=100, remaining=100)
    assert store.get("2026-09-27").force_reload is False


def test_day_picker_shows_remaining_and_reset() -> None:
    days = moscow_recent_days(5)
    progress = {
        days[0].isoformat(): DayProgress(
            day=days[0].isoformat(), last_total=10, last_remaining=3
        ),
        days[1].isoformat(): DayProgress(
            day=days[1].isoformat(), last_total=8, last_remaining=0
        ),
    }
    markup = day_picker(progress_by_day=progress, written_by_day={days[2].isoformat(): 4})
    labels = [btn.text for row in markup.inline_keyboard for btn in row]
    assert any("ост. 3" in text for text in labels)
    assert any("✓" in text for text in labels)
    assert any("зап. 4" in text for text in labels)
    assert any(btn.callback_data == "reset:menu" for row in markup.inline_keyboard for btn in row)

    reset_markup = day_picker(mode="reset")
    assert all(
        (btn.callback_data or "").startswith("resetday:")
        or btn.callback_data == "reset:cancel"
        for row in reset_markup.inline_keyboard
        for btn in row
    )


def test_filter_skips_written_and_counts(tmp_path: Path) -> None:
    sheet = LocalSheetStore(tmp_path / "s.csv")
    card = ReviewCard(
        card_id="1",
        answer_type="FAQ",
        answered_at="2026-09-27 12:00:00",
        player_name="P",
        player_id="1",
        question="q",
        admin_name="A",
        answer="ans",
    )
    other = ReviewCard(
        card_id="2",
        answer_type="FAQ",
        answered_at="2026-09-27 13:00:00",
        player_name="P",
        player_id="1",
        question="q2",
        admin_name="B",
        answer="ans2",
    )
    sheet.append_verdict(card, "Выговор")
    filtered = sheet.filter_new_cards([card, other])
    assert len(filtered) == 1
    assert filtered[0].admin_name == "B"
    assert sheet.written_counts_by_date()["2026-09-27"] == 1
