from __future__ import annotations

from datetime import timedelta

from bot.keyboards import day_picker
from bot.services.panel import moscow_recent_days, moscow_today


def test_moscow_recent_days_newest_first() -> None:
    days = moscow_recent_days(5)
    assert len(days) == 5
    assert days[0] == moscow_today()
    assert days[-1] == moscow_today() - timedelta(days=4)
    assert days == sorted(days, reverse=True)


def test_day_picker_five_iso_callbacks() -> None:
    markup = day_picker(days=5)
    callbacks = [
        btn.callback_data
        for row in markup.inline_keyboard
        for btn in row
    ]
    assert len(callbacks) == 5
    expected = {f"day:{d.isoformat()}" for d in moscow_recent_days(5)}
    assert set(callbacks) == expected
    labels = [btn.text for row in markup.inline_keyboard for btn in row]
    assert any(text.startswith("Сегодня") for text in labels)
    assert any(text.startswith("Вчера") for text in labels)
    # Remaining three use weekday · dd.mm
    assert sum("·" in text for text in labels) == 5
